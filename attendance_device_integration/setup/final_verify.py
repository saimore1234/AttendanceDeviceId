import frappe


def execute():
	print("=== Installed apps ===")
	print(frappe.get_installed_apps())

	print("\n=== DocTypes ===")
	for dt in [
		"Attendance Device", "Attendance Device Credential", "Attendance Device Mapping",
		"Attendance Raw Log", "Attendance Sync Log", "Attendance Integration Settings",
		"Attendance Device Command Log",
	]:
		exists = frappe.db.exists("DocType", dt)
		is_single = exists and frappe.get_meta(dt).issingle
		count = "N/A (Single)" if is_single else (frappe.db.count(dt) if exists else "N/A")
		print(f"  {dt}: exists={bool(exists)} row_count={count}")

	print("\n=== Roles ===")
	for role in ("Attendance Integration Manager", "Attendance Integration User"):
		print(f"  {role}: exists={bool(frappe.db.exists('Role', role))}")

	print("\n=== Workspace ===")
	print("  Attendance Device Integration exists:", bool(frappe.db.exists("Workspace", "Attendance Device Integration")))

	print("\n=== Reports ===")
	reports = frappe.get_all("Report", filters={"module": "Attendance Device Integration"}, pluck="name")
	print(f"  {len(reports)} reports: {sorted(reports)}")

	print("\n=== Scheduler event registered ===")
	events = frappe.get_hooks("scheduler_events")
	print("  'all' bucket:", [e for e in events.get("all", []) if "attendance_device_integration" in e])

	print("\n=== Whitelisted API endpoints ===")
	from attendance_device_integration.api import devices, webhook
	for fn in ["test_connection", "get_device_info", "get_device_users", "sync_device_users",
			   "get_attendance_logs", "sync_device", "clear_device_logs", "get_device_time",
			   "set_device_time", "restart_device", "auto_match_preview"]:
		assert hasattr(devices, fn), f"missing devices.{fn}"
	assert hasattr(webhook, "device_webhook")
	print("  all endpoints present")

	print("\n=== Adapter registry ===")
	from attendance_device_integration.device_adapters.registry import DEVICE_ADAPTERS
	for protocol, cls in DEVICE_ADAPTERS.items():
		print(f"  {protocol:30s} -> {cls.__name__}")

	print("\n=== Employee Checkin compatibility ===")
	from attendance_device_integration.services.checkin_service import employee_checkin_available
	print("  Employee Checkin available:", employee_checkin_available())

	print("\nALL CHECKS PASSED")
