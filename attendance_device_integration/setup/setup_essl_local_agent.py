
import secrets

import frappe


def execute():
    frappe.set_user("Administrator")

    devices = [
        "BioFace-MSD1K",
        "BioFace-MSD1K-02",
    ]

    for device_name in devices:
        if not frappe.db.exists("Attendance Device", device_name):
            print(f"Device not found: {device_name}")
            continue

        device = frappe.get_doc("Attendance Device", device_name)

        device.connection_mode = "Local Agent"

        # Reuse existing token; generate only if missing.
        if not device.get_password("local_agent_token"):
            device.local_agent_token = secrets.token_urlsafe(32)

        device.save(ignore_permissions=True)

        print(f"Configured Local Agent for: {device_name}")

    frappe.db.commit()

    print("Mantra BioFace Local Agent configuration completed.")
    print("Configure the corresponding token in the Windows Agent config.json.")
    print("Keep the existing Local Agent URL and device IP settings.")


