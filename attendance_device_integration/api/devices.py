"""Whitelisted API surface for device operations. Every endpoint checks
permissions explicitly and never executes arbitrary input as code."""

from __future__ import annotations

import frappe

from attendance_device_integration.device_adapters.base import AdapterError
from attendance_device_integration.device_adapters.registry import get_adapter_for_device
from attendance_device_integration.services import credential_service, mapping_service, sync_service


def _require_manager():
	if not (frappe.has_permission("Attendance Device", "write")):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


def _get_device_and_adapter(device_name):
	device = frappe.get_doc("Attendance Device", device_name)
	credential = credential_service.load_credential(device.name)
	return device, get_adapter_for_device(device, credential)


def _log_command(device, command, status, response=None, error=None):
	frappe.get_doc({
		"doctype": "Attendance Device Command Log",
		"device": device, "command": command, "status": status,
		"completed_at": frappe.utils.now_datetime(),
		"response": response, "error": error,
	}).insert(ignore_permissions=True)
	frappe.db.commit()


@frappe.whitelist()
def test_connection(device: str):
	_require_manager()
	try:
		_, adapter = _get_device_and_adapter(device)
	except AdapterError as e:
		result = {"success": False, "error": str(e), "error_code": e.error_code}
		_log_command(device, "Test Connection", "Failed", error=str(e))
		return result

	result = adapter.test_connection()
	frappe.db.set_value("Attendance Device", device, "last_connection_test", frappe.utils.now_datetime(), update_modified=False)
	_log_command(device, "Test Connection", "Success" if result.get("success") else "Failed",
				 response=frappe.as_json(result) if result.get("success") else None,
				 error=result.get("error"))
	return result


@frappe.whitelist()
def get_device_info(device: str):
	_require_manager()
	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		info = adapter.get_device_info()
		return {"success": True, **info.__dict__}
	except AdapterError as e:
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def get_device_users(device: str):
	_require_manager()
	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		users = adapter.get_users()
		return {"success": True, "users": [u.__dict__ for u in users]}
	except AdapterError as e:
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def sync_device_users(device: str, create_missing_employees: bool = False):
	"""Pulls device users and reports which already map to an Employee vs
	not - never auto-creates an Employee unless explicitly asked."""
	_require_manager()
	result = get_device_users(device)
	if not result.get("success"):
		return result

	mapped, unmapped = [], []
	for user in result["users"]:
		employee = mapping_service.resolve_employee(device, user["device_user_id"])
		(mapped if employee else unmapped).append({**user, "employee": employee})

	created = []
	if create_missing_employees and unmapped:
		for user in unmapped:
			frappe.throw(frappe._(
				"Creating Employees automatically is not enabled by default and requires explicit "
				"confirmation per employee - use the Attendance Device Mapping list to map {0} manually, "
				"or enable + confirm employee creation from the Setup Wizard."
			).format(user["device_user_id"]))

	return {"success": True, "mapped": mapped, "unmapped": unmapped, "created": created}


@frappe.whitelist()
def get_attendance_logs(device: str, start_date: str = None, end_date: str = None):
	_require_manager()
	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		if start_date and end_date:
			punches = adapter.get_attendance_logs_by_date(start_date, end_date)
		else:
			punches = adapter.get_attendance_logs()
		return {"success": True, "count": len(punches), "punches": [p.__dict__ for p in punches[:200]]}
	except AdapterError as e:
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def sync_device(device: str, sync_type: str = "Manual", start_date: str = None, end_date: str = None):
	frappe.has_permission("Attendance Device", "read", throw=True)
	return sync_service.sync_device(device, sync_type=sync_type, start_date=start_date, end_date=end_date)


@frappe.whitelist()
def clear_device_logs(device: str, confirm: bool = False):
	_require_manager()
	if not confirm:
		frappe.throw(frappe._("Clearing device logs is destructive - pass confirm=1 to proceed"))

	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		adapter.clear_attendance_logs()
		_log_command(device, "Clear Logs", "Success")
		return {"success": True}
	except AdapterError as e:
		_log_command(device, "Clear Logs", "Failed", error=str(e))
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def get_device_time(device: str):
	_require_manager()
	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		device_time = adapter.get_device_time()
		server_time = frappe.utils.now_datetime()
		diff_seconds = abs((device_time - server_time).total_seconds()) if device_time else None
		settings = frappe.get_single("Attendance Integration Settings")
		return {
			"success": True, "device_time": str(device_time), "server_time": str(server_time),
			"difference_seconds": diff_seconds,
			"warning": bool(diff_seconds and diff_seconds > (settings.time_difference_warning_threshold or 300)),
		}
	except AdapterError as e:
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def set_device_time(device: str):
	_require_manager()
	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		adapter.set_device_time(frappe.utils.now_datetime())
		_log_command(device, "Set Time", "Success")
		return {"success": True}
	except AdapterError as e:
		_log_command(device, "Set Time", "Failed", error=str(e))
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def restart_device(device: str, confirm: bool = False):
	_require_manager()
	if not confirm:
		frappe.throw(frappe._("Restarting the device will interrupt it - pass confirm=1 to proceed"))
	_, adapter = _get_device_and_adapter(device)
	try:
		adapter.connect()
		adapter.restart_device()
		_log_command(device, "Restart Device", "Success")
		return {"success": True}
	except AdapterError as e:
		_log_command(device, "Restart Device", "Failed", error=str(e))
		return {"success": False, "error": str(e), "error_code": e.error_code}
	finally:
		try:
			adapter.disconnect()
		except Exception:
			pass


@frappe.whitelist()
def auto_match_preview(device: str):
	_require_manager()
	return mapping_service.auto_match_summary(device)
