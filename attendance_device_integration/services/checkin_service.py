"""Attendance Raw Log -> Employee Checkin.

This is the only place that creates Employee Checkin records, and it
never creates Attendance directly (per the required flow: Device -> Raw
Log -> Employee Mapping -> Employee Checkin -> HRMS shift/attendance
processing -> Attendance). Whether Employee Checkin exists at all is
detected at runtime so this works across HRMS versions/installations
that may not have it.
"""

from __future__ import annotations

import frappe

from attendance_device_integration.utils.logging import log_checkin
from attendance_device_integration.utils.timezone_utils import to_system_timezone


def employee_checkin_available() -> bool:
	return bool(frappe.db.exists("DocType", "Employee Checkin"))


def _determine_log_type(raw_log, settings) -> str:
	direction = (raw_log.direction or "UNKNOWN").upper()
	if direction in ("IN", "OUT"):
		return direction

	pairing_mode = raw_log.get("punch_pairing_mode") or settings.punch_pairing_mode or "Use Device Direction"
	if pairing_mode != "Sequential IN/OUT":
		return ""  # let HRMS infer / leave blank, matches "AUTO/UNKNOWN" from spec

	if not frappe.db.exists("DocType", "Employee Checkin"):
		return ""

	existing_today = frappe.db.count(
		"Employee Checkin",
		{"employee": raw_log.employee, "time": ["between", [
			raw_log.punch_datetime.replace(hour=0, minute=0, second=0, microsecond=0),
			raw_log.punch_datetime.replace(hour=23, minute=59, second=59, microsecond=999999),
		]]},
	)
	return "IN" if existing_today % 2 == 0 else "OUT"


def create_employee_checkin(raw_log) -> str:
	"""raw_log: an Attendance Raw Log document, already saved, with
	`employee` resolved. Returns the Employee Checkin name, or None if
	checkin creation is disabled/unavailable. Idempotent: if this raw log
	already has an employee_checkin linked, returns that instead of
	creating a second one."""

	if raw_log.employee_checkin:
		return raw_log.employee_checkin

	if not employee_checkin_available():
		log_checkin("Employee Checkin DocType not found on this HRMS install - skipping checkin creation")
		return None

	settings = frappe.get_single("Attendance Integration Settings")
	if not settings.create_employee_checkin:
		return None

	if not raw_log.employee:
		return None

	device_timezone = frappe.db.get_value("Attendance Device", raw_log.device, "device_timezone") or "UTC"
	try:
		checkin_time = to_system_timezone(raw_log.punch_datetime, device_timezone)
	except ValueError:
		checkin_time = raw_log.punch_datetime  # fall back to naive device time rather than fail the whole sync

	log_type = _determine_log_type(raw_log, settings)

	checkin = frappe.get_doc({
		"doctype": "Employee Checkin",
		"employee": raw_log.employee,
		"time": checkin_time,
		"log_type": log_type or None,
		"device_id": raw_log.device,
	})
	checkin.insert(ignore_permissions=True)

	log_checkin(f"Created {checkin.name} for employee {raw_log.employee} at {checkin_time}")
	return checkin.name
