import secrets

import frappe


def execute():
	frappe.set_user("Administrator")

	device_name = "Chintamani ESSL X990"
	token = secrets.token_urlsafe(32)

	device = frappe.get_doc("Attendance Device", device_name)
	device.connection_mode = "Local Agent"
	# NOTE: local_agent_url is left blank here - fill it in once you have
	# the actual reachable URL (port-forward / tunnel) for the agent.
	device.save(ignore_permissions=True)

	if frappe.db.exists("Attendance Device Credential", device_name):
		cred = frappe.get_doc("Attendance Device Credential", device_name)
	else:
		cred = frappe.get_doc({"doctype": "Attendance Device Credential", "device": device_name})
	cred.bearer_token = token
	cred.save(ignore_permissions=True)
	frappe.db.commit()

	print(f"Device {device_name} set to Local Agent mode.")
	print(f"Generated token (put this EXACT value in config.json on the agent PC): {token}")
	print("Remaining steps:")
	print("  1. Copy apps/attendance_device_integration/local_agent/ to a PC on the device's network.")
	print("  2. pip install -r requirements.txt there.")
	print("  3. config.json: set this token.")
	print("  4. Run: python agent.py --config config.json")
	print("  5. Expose it (port-forward / tunnel) and set Local Agent URL on the Attendance Device record.")
