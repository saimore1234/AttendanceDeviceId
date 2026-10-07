"""Device timezone -> system timezone conversion.

A device's clock may be set to its own local timezone (configured per
Attendance Device as device_timezone), independent of the ERPNext
server's or company's timezone. We store both: the raw datetime exactly
as the device reported it (Attendance Raw Log.punch_datetime, naive,
device-local) and only convert when writing into Employee Checkin, which
Frappe stores as system-time.

Uses pytz (bundled with Frappe) rather than zoneinfo: zoneinfo reads the
OS tz database, and newer distros ship legacy aliases such as
"Asia/Calcutta" - Frappe's own default - only in an optional package.
"""

from __future__ import annotations

from datetime import datetime

import frappe
import pytz


def _get_zone(name: str):
	try:
		return pytz.timezone(name or "UTC")
	except pytz.UnknownTimeZoneError:
		raise ValueError(f"Unknown timezone: {name!r}")


def to_system_timezone(dt: datetime, device_timezone: str) -> datetime:
	"""Interpret `dt` as being in `device_timezone`, return the equivalent
	naive datetime in the system timezone (what Frappe expects to store)."""
	if dt is None:
		return None

	device_tz = _get_zone(device_timezone)
	system_tz = _get_zone(frappe.utils.get_system_timezone())

	aware = device_tz.localize(dt)
	converted = aware.astimezone(system_tz)
	return converted.replace(tzinfo=None)


def now_in_timezone(device_timezone: str) -> datetime:
	"""Current wall-clock time in `device_timezone`, naive - what a device
	clock should be set to."""
	return datetime.now(_get_zone(device_timezone)).replace(tzinfo=None, microsecond=0)


def is_valid_timezone(name: str) -> bool:
	try:
		_get_zone(name)
		return True
	except ValueError:
		return False
