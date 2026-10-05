"""Webhook endpoint for push-mode devices (ADMS Push and any other device
that calls out to us instead of waiting to be polled).

Flow (never bypassed):

	Webhook -> Validate (device auth) -> Normalize -> Raw Log (via the
	same ingest_punch() duplicate-check/mapping path as polled sync) ->
	Employee Mapping -> Employee Checkin

Untrusted input never creates Attendance directly - only a Raw Log, and
only an Employee Checkin once mapping succeeds, identical to the polled
flow. A device can only push to itself: the token must match the
specific device's stored credential.
"""

from __future__ import annotations

from datetime import datetime

import frappe

from attendance_device_integration.device_adapters.base import RawPunch
from attendance_device_integration.services import credential_service, sync_service
from attendance_device_integration.utils.logging import log_sync


def _parse_datetime(value):
	if isinstance(value, datetime):
		return value
	if isinstance(value, (int, float)):
		return datetime.fromtimestamp(value)
	for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%d-%m-%Y %H:%M:%S"):
		try:
			return datetime.strptime(str(value), fmt)
		except ValueError:
			continue
	frappe.throw(frappe._("Could not parse punch_datetime: {0}").format(value))


def _authenticate(device_name: str) -> None:
	token = None
	auth_header = frappe.get_request_header("Authorization") or ""
	if auth_header.startswith("Bearer "):
		token = auth_header[len("Bearer "):]
	if not token:
		token = frappe.form_dict.get("token")

	if not token:
		frappe.throw(frappe._("Missing device token"), frappe.AuthenticationError)

	credential = credential_service.load_credential(device_name)
	valid_tokens = {t for t in (credential.get("bearer_token"), credential.get("api_key")) if t}
	if not valid_tokens or token not in valid_tokens:
		log_sync(f"Webhook auth failed for device {device_name}")
		frappe.throw(frappe._("Invalid device token"), frappe.AuthenticationError)


def _punch_from_payload(record: dict) -> RawPunch:
	device_user_id = record.get("device_user_id") or record.get("user_id") or record.get("employee_id")
	punch_dt_raw = record.get("punch_datetime") or record.get("timestamp") or record.get("time")
	if not device_user_id or not punch_dt_raw:
		frappe.throw(frappe._("Each punch requires device_user_id and punch_datetime"))

	return RawPunch(
		device_user_id=str(device_user_id),
		punch_datetime=_parse_datetime(punch_dt_raw),
		punch_type=str(record.get("punch_type") or ""),
		direction=str(record.get("direction") or "UNKNOWN").upper(),
		transaction_id=str(record.get("transaction_id") or "") or None,
		device_transaction_id=str(record.get("device_transaction_id") or "") or None,
		verification_type=record.get("verification_type"),
		work_code=record.get("work_code"),
		raw=frappe.as_json(record),
	)


@frappe.whitelist(allow_guest=True)
def device_webhook(device: str = None, **kwargs):
	"""POST body: either a single punch object, or {"punches": [...]}.
	Query/body must include `device` (Attendance Device name) and the
	request must carry that device's token via `Authorization: Bearer`."""

	if not device:
		frappe.throw(frappe._("Missing 'device'"))
	if not frappe.db.exists("Attendance Device", device):
		frappe.throw(frappe._("Unknown device: {0}").format(device))

	_authenticate(device)

	device_doc = frappe.db.get_value("Attendance Device", device, ["enabled", "protocol_type"], as_dict=True)
	if not device_doc.enabled:
		frappe.throw(frappe._("Device {0} is disabled").format(device))

	payload = frappe.request.get_json(silent=True) or frappe.form_dict
	records = payload.get("punches") if isinstance(payload, dict) and payload.get("punches") else [payload]

	inserted, duplicates, errors = 0, 0, 0
	for record in records:
		if not isinstance(record, dict):
			continue
		try:
			punch = _punch_from_payload(record)
			result = sync_service.ingest_punch(device, punch, source="Webhook")
			if result["status"] == "duplicate":
				duplicates += 1
			else:
				inserted += 1
		except Exception:
			errors += 1

	frappe.db.commit()
	frappe.db.set_value("Attendance Device", device, "last_sync_datetime", frappe.utils.now_datetime(), update_modified=False)
	log_sync(f"Webhook received {len(records)} record(s) for device {device}: "
			 f"inserted={inserted} duplicates={duplicates} errors={errors}")

	return {"success": True, "received": len(records), "inserted": inserted, "duplicates": duplicates, "errors": errors}
