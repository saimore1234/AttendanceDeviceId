"""Device timezone -> system timezone conversion.

A device's clock may be set to its own local timezone (configured per
Attendance Device as device_timezone), independent of the ERPNext
server's or company's timezone. We store both: the raw datetime exactly
as the device reported it (Attendance Raw Log.punch_datetime, naive,
device-local) and only convert when writing into Employee Checkin, which
Frappe stores as system-time.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe


def to_system_timezone(dt: datetime, device_timezone: str) -> datetime:
	"""Interpret `dt` as being in `device_timezone`, return the equivalent
	naive datetime in the system timezone (what Frappe expects to store)."""
	if dt is None:
		return None

	system_tz_name = frappe.utils.get_system_timezone() if hasattr(frappe.utils, "get_system_timezone") else "UTC"

	try:
		device_tz = ZoneInfo(device_timezone or "UTC")
	except ZoneInfoNotFoundError:
		raise ValueError(f"Unknown timezone: {device_timezone!r}")

	try:
		system_tz = ZoneInfo(system_tz_name)
	except ZoneInfoNotFoundError:
		system_tz = ZoneInfo("UTC")

	aware = dt.replace(tzinfo=device_tz)
	converted = aware.astimezone(system_tz)
	return converted.replace(tzinfo=None)


def is_valid_timezone(name: str) -> bool:
	try:
		ZoneInfo(name)
		return True
	except ZoneInfoNotFoundError:
		return False
