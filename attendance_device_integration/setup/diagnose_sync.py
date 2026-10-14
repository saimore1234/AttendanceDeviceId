"""Read-only health check for device sync -> raw logs -> Employee Checkin.

bench --site <site> execute attendance_device_integration.setup.diagnose_sync.run
bench --site <site> execute attendance_device_integration.setup.diagnose_sync.run --kwargs "{'device': 'Chintamani ESSL X990'}"

Changes nothing: it reads the database and reads (never clears) the device.
"""

import frappe
from frappe.utils import getdate, now_datetime

from attendance_device_integration.device_adapters.registry import get_adapter_for_device
from attendance_device_integration.services import credential_service


def run(device=None):
	today = getdate()
	print(f"Server time: {now_datetime()}")
	print(f"Scheduler enabled: {frappe.db.get_single_value('System Settings', 'enable_scheduler')}")
	s = frappe.get_single("Attendance Integration Settings")
	print(
		f"Settings: integration={s.enable_integration} background_sync={s.enable_background_sync} "
		f"create_checkin={s.create_employee_checkin} pairing={s.punch_pairing_mode} "
		f"log_retention_days={s.log_retention_days}"
	)

	names = [device] if device else frappe.get_all("Attendance Device", filters={"enabled": 1}, pluck="name")
	for name in names:
		d = frappe.get_doc("Attendance Device", name)
		print(f"\n=== {name} ===")
		print(
			f"protocol={d.protocol_type} mode={d.connection_mode} ip={d.ip_address}:{d.port} tz={d.device_timezone} "
			f"auto_sync={d.auto_sync_enabled} interval={d.sync_interval}"
		)
		print(f"last_sync={d.last_sync_datetime} status={d.last_sync_status} msg={d.last_sync_message}")

		print("Recent sync logs:")
		for r in frappe.get_all(
			"Attendance Sync Log",
			filters={"device": name},
			fields=["name", "sync_type", "status", "sync_started_at", "records_fetched", "records_inserted",
					"records_duplicated", "records_failed", "error_message"],
			order_by="creation desc",
			limit=8,
		):
			print(f"  {r.name} {r.sync_type:<10} {r.status:<8} {r.sync_started_at} fetched={r.records_fetched} "
				  f"inserted={r.records_inserted} dup={r.records_duplicated} failed={r.records_failed} {r.error_message or ''}")

		print(f"Raw logs punched today ({today}) by status:")
		for r in frappe.db.sql(
			"""select processing_status, count(*) n from `tabAttendance Raw Log`
			where device=%s and punch_date=%s group by processing_status""",
			(name, today),
			as_dict=True,
		):
			print(f"  {r.processing_status}: {r.n}")
		for r in frappe.get_all(
			"Attendance Raw Log",
			filters={"device": name, "punch_date": today, "processing_status": ["!=", "Processed"]},
			fields=["device_user_id", "punch_datetime", "processing_status", "processing_message"],
			order_by="punch_datetime desc",
			limit=10,
		):
			print(f"  NOT PROCESSED: user={r.device_user_id} at {r.punch_datetime} {r.processing_status}: {r.processing_message}")

		print(f"Employee Checkins today from this device: "
			  f"{frappe.db.count('Employee Checkin', {'device_id': name, 'time': ['>=', today]})}")

		print("Reading the device directly (read-only)...")
		try:
			adapter = get_adapter_for_device(d, credential_service.load_credential(name))
			adapter.connect()
			try:
				try:
					print(f"  device clock: {adapter.get_device_time()}  (server: {now_datetime()})")
				except Exception as e:
					print(f"  device clock: unavailable ({e})")
				punches = adapter.get_attendance_logs()
			finally:
				adapter.disconnect()
			print(f"  records on device: {len(punches)}")
			if punches:
				punches.sort(key=lambda p: p.punch_datetime)
				print(f"  oldest: {punches[0].punch_datetime}  newest: {punches[-1].punch_datetime}")
				todays = [p for p in punches if p.punch_datetime.date() == today]
				print(f"  punches dated today on device: {len(todays)}")
				for p in punches[-5:]:
					print(f"  latest: user={p.device_user_id} at {p.punch_datetime} direction={p.direction}")
		except Exception as e:
			print(f"  could not read device: {e}")
