"""Device User ID -> Employee resolution.

Priority order:
	1. An explicit, active Attendance Device Mapping row for this exact
	   device + device_user_id (always wins - administrator overrides
	   auto-matching).
	2. Auto-match using the rule configured in Attendance Integration
	   Settings (Employee ID / Employee Number / a custom field).

Never creates a fake/placeholder Employee. If nothing matches, the caller
marks the raw log as "Unmapped Employee" and moves on - visible in the
Unmapped Device Employees report, not silently dropped.
"""

from __future__ import annotations

from typing import Optional

import frappe

from attendance_device_integration.utils.logging import log_mapping


def resolve_employee(device: str, device_user_id: str) -> Optional[str]:
	if not device_user_id:
		return None

	explicit = frappe.db.get_value(
		"Attendance Device Mapping",
		{"device": device, "device_user_id": device_user_id, "active": 1},
		"employee",
	)
	if explicit:
		return explicit

	settings = frappe.get_single("Attendance Integration Settings")
	rule = settings.auto_match_rule or "Attendance Device ID (Employee field)"

	if rule == "Attendance Device ID (Employee field)":
		# The standard HRMS Employee field (Attendance & Leaves tab) built
		# for exactly this - maintain the device's user ID on the Employee
		# master itself, no separate mapping record needed.
		return frappe.db.get_value("Employee", {"attendance_device_id": device_user_id}, "name")

	if rule == "Employee ID":
		if frappe.db.exists("Employee", device_user_id):
			return device_user_id
		return None

	if rule == "Employee Number":
		return frappe.db.get_value("Employee", {"employee_number": device_user_id}, "name")

	if rule == "Custom Field" and settings.auto_match_custom_field:
		try:
			return frappe.db.get_value("Employee", {settings.auto_match_custom_field: device_user_id}, "name")
		except Exception:
			log_mapping(f"Custom auto-match field {settings.auto_match_custom_field!r} is invalid")
			return None

	return None


def auto_match_summary(device: str) -> dict:
	"""Preview how many unmapped raw logs for this device WOULD resolve
	under the current auto-match rule, without changing anything -
	useful for the "Auto Match" button before committing."""
	unmapped = frappe.get_all(
		"Attendance Raw Log",
		filters={"device": device, "processing_status": "Unmapped Employee"},
		fields=["name", "device_user_id"],
	)
	would_match = 0
	still_unmapped = []
	for row in unmapped:
		if resolve_employee(device, row.device_user_id):
			would_match += 1
		else:
			still_unmapped.append(row.device_user_id)

	return {
		"total_unmapped": len(unmapped),
		"would_match": would_match,
		"still_unmapped_user_ids": sorted(set(still_unmapped)),
	}
