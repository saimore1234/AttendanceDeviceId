"""Background sync scheduling.

Runs every minute (cheap check) and enqueues an actual sync job only for
devices whose OWN configured Sync Interval has elapsed - the interval is
per-device and admin-configurable, never a hardcoded global cadence.
Each device's sync runs as a separate background job (frappe.enqueue),
so a slow/stuck device never blocks the web request or other devices.
"""

from __future__ import annotations

import frappe

from attendance_device_integration.utils.logging import log_sync


def sync_due_devices():
	settings = frappe.get_single("Attendance Integration Settings")
	if not settings.enable_integration or not settings.enable_background_sync:
		return

	now = frappe.utils.now_datetime()
	devices = frappe.get_all(
		"Attendance Device",
		filters={"enabled": 1, "auto_sync_enabled": 1},
		fields=["name", "sync_interval", "last_sync_datetime"],
	)

	for device in devices:
		interval_minutes = device.sync_interval or settings.default_sync_interval or 5
		due = (
			not device.last_sync_datetime
			or (now - device.last_sync_datetime).total_seconds() >= interval_minutes * 60
		)
		if not due:
			continue

		if frappe.db.exists("Attendance Sync Log", {"device": device.name, "status": "Running"}):
			continue  # previous job for this device is still running - don't pile up

		log_sync(f"Enqueuing scheduled sync for {device.name}")
		frappe.enqueue(
			"attendance_device_integration.services.sync_service.sync_device",
			queue="long",
			job_name=f"attendance-sync-{device.name}",
			device_name=device.name,
			sync_type="Scheduled",
		)
