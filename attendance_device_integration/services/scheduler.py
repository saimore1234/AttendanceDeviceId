"""Background sync scheduling.

Runs every minute (cheap check) and enqueues an actual sync job only for
devices whose OWN configured Sync Interval has elapsed - the interval is
per-device and admin-configurable, never a hardcoded global cadence.
Each device's sync runs as a separate background job (frappe.enqueue),
so a slow/stuck device never blocks the web request or other devices.
"""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils.background_jobs import is_job_enqueued

from attendance_device_integration.utils.constants import SYNC_STATUS_FAILED, SYNC_STATUS_RUNNING
from attendance_device_integration.utils.logging import log_sync

# A sync log still "Running" after this long belongs to a job that died
# (worker killed, server restart). Left alone it would block the device's
# scheduled sync forever.
STALE_RUNNING_MINUTES = 30


def sync_due_devices():
	settings = frappe.get_single("Attendance Integration Settings")
	if not settings.enable_integration or not settings.enable_background_sync:
		return

	now = frappe.utils.now_datetime()
	fail_stale_running_logs(now)

	devices = frappe.get_all(
		"Attendance Device",
		filters={"enabled": 1, "auto_sync_enabled": 1},
		fields=["name", "sync_interval", "last_sync_datetime"],
	)

	for device in devices:
		interval_minutes = device.sync_interval or settings.default_sync_interval or 2
		# Measure from the last attempt, not the last success, so an offline
		# device is retried once per interval rather than on every tick.
		last_attempt = max(
			filter(None, [device.last_sync_datetime, get_last_attempt(device.name)]),
			default=None,
		)
		if last_attempt and (now - last_attempt).total_seconds() < interval_minutes * 60:
			continue

		job_id = f"attendance-sync-{device.name}"
		if is_job_enqueued(job_id):
			continue  # previous job is still queued or running - don't pile up
		if frappe.db.exists("Attendance Sync Log", {"device": device.name, "status": SYNC_STATUS_RUNNING}):
			continue  # a manual sync is in progress

		log_sync(f"Enqueuing scheduled sync for {device.name}")
		frappe.enqueue(
			"attendance_device_integration.services.sync_service.sync_device",
			queue="long",
			job_id=job_id,
			deduplicate=True,
			device_name=device.name,
			sync_type="Scheduled",
		)


def get_last_attempt(device_name):
	return frappe.db.get_value(
		"Attendance Sync Log", {"device": device_name}, "sync_started_at", order_by="sync_started_at desc"
	)


def fail_stale_running_logs(now):
	cutoff = now - timedelta(minutes=STALE_RUNNING_MINUTES)
	for name in frappe.get_all(
		"Attendance Sync Log",
		filters={"status": SYNC_STATUS_RUNNING, "sync_started_at": ["<", cutoff]},
		pluck="name",
	):
		frappe.db.set_value(
			"Attendance Sync Log",
			name,
			{
				"status": SYNC_STATUS_FAILED,
				"error_message": f"Sync job did not finish within {STALE_RUNNING_MINUTES} minutes",
				"sync_completed_at": now,
			},
			update_modified=False,
		)
		log_sync(f"Marked stale running sync log {name} as failed")
	frappe.db.commit()
