"""Centralized sync engine.

sync_device() is the one function that drives the full flow for a single
device:

	Attendance Device -> Device Adapter -> Raw Log -> Duplicate Check ->
	Employee Mapping -> Employee Checkin

It never raises out to its caller for device-side failures (offline,
auth failed, unsupported protocol, ...) - those are captured in the
Attendance Sync Log and the Attendance Device's last_sync_* fields, so
one bad device never stops the scheduler from syncing the rest.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe

from attendance_device_integration.device_adapters.base import AdapterError
from attendance_device_integration.device_adapters.registry import get_adapter_for_device
from attendance_device_integration.services import checkin_service, credential_service, mapping_service
from attendance_device_integration.utils.constants import (
	LAST_SYNC_FAILED, LAST_SYNC_OFFLINE, LAST_SYNC_SUCCESS, LAST_SYNC_PARTIAL,
	PROCESSING_STATUS_ERROR, PROCESSING_STATUS_PROCESSED, PROCESSING_STATUS_UNMAPPED,
	SYNC_STATUS_FAILED, SYNC_STATUS_PARTIAL, SYNC_STATUS_RUNNING, SYNC_STATUS_SUCCESS,
)
from attendance_device_integration.utils.hashing import compute_unique_hash
from attendance_device_integration.utils.logging import log_error, log_sync


def sync_device(device_name: str, sync_type: str = "Manual", start_date=None, end_date=None) -> dict:
	if not frappe.db.exists("Attendance Device", device_name):
		return {"success": False, "error": f"Attendance Device {device_name!r} does not exist"}

	device = frappe.get_doc("Attendance Device", device_name)
	if not device.enabled:
		return {"success": False, "error": f"Device {device_name!r} is disabled"}

	settings = frappe.get_single("Attendance Integration Settings")
	if not settings.enable_integration:
		return {"success": False, "error": "Attendance Integration is disabled in settings"}

	sync_log = frappe.get_doc({
		"doctype": "Attendance Sync Log",
		"device": device.name,
		"sync_type": sync_type,
		"status": SYNC_STATUS_RUNNING,
		"sync_started_at": frappe.utils.now_datetime(),
		"start_datetime": start_date,
		"end_datetime": end_date,
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	log_sync(f"Starting {sync_type} sync for device {device.name}")

	counters = {"fetched": 0, "inserted": 0, "duplicated": 0, "processed": 0, "failed": 0}
	error_message = None

	try:
		credential = credential_service.load_credential(device.name)
		adapter = get_adapter_for_device(device, credential)

		try:
			adapter.connect()
		except AdapterError as e:
			device.db_set("last_sync_status", LAST_SYNC_OFFLINE, update_modified=False)
			device.db_set("last_sync_message", str(e), update_modified=False)
			sync_log.status = SYNC_STATUS_FAILED
			sync_log.error_message = str(e)
			sync_log.sync_completed_at = frappe.utils.now_datetime()
			sync_log.save(ignore_permissions=True)
			frappe.db.commit()
			log_sync(f"Device {device.name} offline/unreachable: {e}")
			return {"success": False, "error": str(e), "error_code": e.error_code}

		try:
			punches = _fetch_punches(adapter, device, sync_type, start_date, end_date)
			counters["fetched"] = len(punches)

			batch_size = int(settings.batch_size or 500)
			for i in range(0, len(punches), batch_size):
				batch = punches[i:i + batch_size]
				_process_batch(device, batch, counters, settings)
				frappe.db.commit()

		finally:
			try:
				adapter.disconnect()
			except Exception:
				pass

		status = SYNC_STATUS_SUCCESS if counters["failed"] == 0 else SYNC_STATUS_PARTIAL
		device.db_set("last_sync_datetime", frappe.utils.now_datetime(), update_modified=False)
		device.db_set("last_successful_sync", frappe.utils.now_datetime(), update_modified=False)
		device.db_set("last_sync_status", LAST_SYNC_SUCCESS if status == SYNC_STATUS_SUCCESS else LAST_SYNC_PARTIAL, update_modified=False)
		device.db_set("last_sync_message",
					  f"Fetched {counters['fetched']}, inserted {counters['inserted']}, "
					  f"duplicates {counters['duplicated']}, failed {counters['failed']}", update_modified=False)

	except AdapterError as e:
		status = SYNC_STATUS_FAILED
		error_message = str(e)
		device.db_set("last_sync_status", LAST_SYNC_FAILED, update_modified=False)
		device.db_set("last_sync_message", error_message, update_modified=False)
		log_error(f"Sync failed for device {device.name}: {e}")
	except Exception as e:
		status = SYNC_STATUS_FAILED
		error_message = f"Unexpected error: {e}"
		device.db_set("last_sync_status", LAST_SYNC_FAILED, update_modified=False)
		device.db_set("last_sync_message", error_message, update_modified=False)
		log_error(f"Unexpected sync failure for device {device.name}: {e}")

	sync_log.status = status
	sync_log.records_fetched = counters["fetched"]
	sync_log.records_inserted = counters["inserted"]
	sync_log.records_duplicated = counters["duplicated"]
	sync_log.records_processed = counters["processed"]
	sync_log.records_failed = counters["failed"]
	sync_log.error_message = error_message
	sync_log.sync_completed_at = frappe.utils.now_datetime()
	sync_log.save(ignore_permissions=True)
	frappe.db.commit()

	log_sync(f"Finished sync for device {device.name}: {counters}")
	return {"success": status != SYNC_STATUS_FAILED, "status": status, **counters, "sync_log": sync_log.name}


def _fetch_punches(adapter, device, sync_type, start_date, end_date):
	if sync_type == "Full Sync" or (start_date and end_date):
		start = start_date or (datetime.now() - timedelta(days=3650))
		end = end_date or datetime.now()
		return adapter.get_attendance_logs_by_date(start, end)

	since = device.last_sync_datetime
	return adapter.get_attendance_logs_since_last_sync(since)


def _process_batch(device, punches, counters, settings):
	for punch in punches:
		try:
			_process_one_punch(device, punch, counters, settings)
		except Exception as e:
			counters["failed"] += 1
			log_error(f"Failed to process punch for device {device.name}, user {punch.device_user_id}: {e}")


def ingest_punch(device_name: str, punch, source: str = "Sync") -> dict:
	"""Single-punch entry point shared by the batch sync loop and the
	webhook handler: duplicate check -> employee mapping -> Raw Log ->
	Employee Checkin. Returns {"status": "duplicate"|"inserted", "raw_log": name|None}.
	"""
	unique_hash = compute_unique_hash(device_name, punch.device_user_id, punch.punch_datetime, punch.transaction_id)

	if frappe.db.exists("Attendance Raw Log", {"unique_hash": unique_hash}):
		return {"status": "duplicate", "raw_log": None}

	employee = mapping_service.resolve_employee(device_name, punch.device_user_id)

	raw_log = frappe.get_doc({
		"doctype": "Attendance Raw Log",
		"device": device_name,
		"device_user_id": punch.device_user_id,
		"employee": employee,
		"punch_datetime": punch.punch_datetime,
		"punch_date": punch.punch_datetime.date(),
		"punch_time": punch.punch_datetime.time(),
		"punch_type": punch.punch_type,
		"direction": punch.direction or "UNKNOWN",
		"verification_type": punch.verification_type,
		"work_code": punch.work_code,
		"transaction_id": punch.transaction_id,
		"device_transaction_id": punch.device_transaction_id,
		"source": source,
		"raw_data": punch.raw,
		"unique_hash": unique_hash,
	})

	if not employee:
		raw_log.processing_status = PROCESSING_STATUS_UNMAPPED
		raw_log.processing_message = f"No Employee mapped for Device User ID {punch.device_user_id!r}"
		raw_log.insert(ignore_permissions=True)
		return {"status": "inserted", "raw_log": raw_log.name, "processed": False}

	raw_log.employee_number = frappe.db.get_value("Employee", employee, "employee_number")
	raw_log.insert(ignore_permissions=True)

	try:
		checkin_name = checkin_service.create_employee_checkin(raw_log)
		raw_log.db_set("employee_checkin", checkin_name, update_modified=False)
		raw_log.db_set("processed", 1, update_modified=False)
		raw_log.db_set("processing_status", PROCESSING_STATUS_PROCESSED, update_modified=False)
		return {"status": "inserted", "raw_log": raw_log.name, "processed": True}
	except Exception as e:
		raw_log.db_set("processing_status", PROCESSING_STATUS_ERROR, update_modified=False)
		raw_log.db_set("processing_message", str(e), update_modified=False)
		log_error(f"Checkin creation failed for raw log {raw_log.name}: {e}")
		return {"status": "inserted", "raw_log": raw_log.name, "processed": False, "error": str(e)}


def _process_one_punch(device, punch, counters, settings):
	result = ingest_punch(device.name, punch, source="Sync")
	if result["status"] == "duplicate":
		counters["duplicated"] += 1
	elif result.get("processed"):
		counters["inserted"] += 1
		counters["processed"] += 1
	elif result.get("error"):
		counters["inserted"] += 1
		counters["failed"] += 1
	else:
		counters["inserted"] += 1  # unmapped employee - inserted, not processed, not an error
