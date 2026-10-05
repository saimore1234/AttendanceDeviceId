"""Demonstrates the exact UX the user asked for: create a device like
their ESSL machine, click Test Connection, see a clear result either way
- never a silent failure or stack trace."""

import frappe

from attendance_device_integration.api import devices as devices_api


def execute():
	frappe.set_user("Administrator")

	name = "_Demo ESSL Device"
	if frappe.db.exists("Attendance Device", name):
		frappe.delete_doc("Attendance Device", name, force=1, ignore_permissions=True)

	frappe.get_doc({
		"doctype": "Attendance Device",
		"device_name": name,
		"device_brand": "ESSL",
		"device_model": "Unknown (user-entered)",
		"protocol_type": "ESSL TCP/IP",
		"ip_address": "192.0.2.123",  # TEST-NET-1, guaranteed unreachable
		"port": 4370,
		"connection_timeout": 2,
		"enabled": 1,
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	result = devices_api.test_connection(name)
	print("TEST CONNECTION RESULT (unreachable device):")
	print(result)
	assert result["success"] is False
	assert "error" in result

	# Also show what SDK-missing looks like (by temporarily hiding the import)
	import attendance_device_integration.device_adapters.zk_protocol as zk_module
	original = zk_module.ZK
	zk_module.ZK = None
	try:
		result2 = devices_api.test_connection(name)
		print("\nTEST CONNECTION RESULT (pyzk not installed, simulated):")
		print(result2)
		assert result2.get("error_code") == "SDK_MISSING"
	finally:
		zk_module.ZK = original

	frappe.delete_doc("Attendance Device", name, force=1, ignore_permissions=True)
	frappe.db.commit()
	print("\nDemo passed - both failure modes are clear, never a silent failure or crash.")
