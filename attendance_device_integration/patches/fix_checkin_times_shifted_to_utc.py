"""Older timezone_utils used zoneinfo, which on newer distros can't resolve
legacy aliases like "Asia/Calcutta" (Frappe's default system timezone) and
silently fell back to UTC - so Employee Checkins were written shifted by the
device's UTC offset. Recompute those checkins from their raw log.

Only checkins whose time exactly equals the old buggy (device -> UTC) value
are touched; anything edited by hand or already correct is left alone."""

import pytz

import frappe
from frappe.utils import get_datetime

from attendance_device_integration.utils.timezone_utils import to_system_timezone


def execute():
	if not frappe.db.exists("DocType", "Employee Checkin"):
		return

	device_tz = dict(frappe.get_all("Attendance Device", fields=["name", "device_timezone"], as_list=True))

	logs = frappe.get_all(
		"Attendance Raw Log",
		filters={"employee_checkin": ("is", "set")},
		fields=["device", "punch_datetime", "employee_checkin"],
	)
	for log in logs:
		tz_name = device_tz.get(log.device) or "UTC"
		try:
			correct = to_system_timezone(get_datetime(log.punch_datetime), tz_name)
			buggy = pytz.timezone(tz_name).localize(get_datetime(log.punch_datetime)).astimezone(pytz.utc).replace(tzinfo=None)
		except (ValueError, pytz.UnknownTimeZoneError):
			continue
		if correct == buggy:
			continue

		checkin = frappe.db.get_value("Employee Checkin", log.employee_checkin, ["time", "attendance"], as_dict=True)
		if not checkin or checkin.attendance or get_datetime(checkin.time) != buggy:
			continue

		try:
			doc = frappe.get_doc("Employee Checkin", log.employee_checkin)
			doc.time = correct
			doc.save(ignore_permissions=True)  # validate() re-fetches the shift
		except Exception:
			frappe.log_error(title=f"Could not fix time on Employee Checkin {log.employee_checkin}")
