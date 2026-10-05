import frappe


def execute():
	frappe.set_user("Administrator")

	name = "Chintamani ESSL X990"
	if frappe.db.exists("Attendance Device", name):
		print("Device already exists, skipping")
		return

	frappe.get_doc({
		"doctype": "Attendance Device",
		"device_name": name,
		"device_brand": "ESSL",
		"device_model": "X990",
		"protocol_type": "ESSL TCP/IP",
		"ip_address": "192.168.0.56",
		"port": 4370,
		"connection_timeout": 10,
		"enabled": 1,
		"active": 1,
		"connection_mode": "Server",
		"device_timezone": "Asia/Kolkata",
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Created Attendance Device: {name}")
