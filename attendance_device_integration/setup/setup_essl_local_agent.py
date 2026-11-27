import secrets
import frappe


def execute():
    frappe.set_user("Administrator")

    devices = [
        "BioFace-MSD1K",
        "BioFace-MSD1K-02",
    ]

    # Reuse an existing token, or generate one shared token.
    shared_token = None

    for device_name in devices:
        if frappe.db.exists("Attendance Device", device_name):
            device = frappe.get_doc("Attendance Device", device_name)
            shared_token = device.get_password("local_agent_token")
            if shared_token:
                break

    if not shared_token:
        shared_token = secrets.token_urlsafe(32)

    for device_name in devices:
        if not frappe.db.exists("Attendance Device", device_name):
            print(f"Device not found: {device_name}")
            continue

        device = frappe.get_doc("Attendance Device", device_name)
        device.connection_mode = "Local Agent"
        device.local_agent_token = shared_token
        device.save(ignore_permissions=True)

        print(f"Configured Local Agent for: {device_name}")

    frappe.db.commit()
    print("Both devices configured with the same Local Agent token.")