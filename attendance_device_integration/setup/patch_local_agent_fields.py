"""Adds Local Agent support to Attendance Device: when the device isn't
reachable directly from wherever ERPNext runs (remote office, different
network), a small standalone agent runs ON that network instead, and
ERPNext talks to the agent over HTTP rather than to the device directly.
"""

import frappe


def execute():
	frappe.set_user("Administrator")
	doc = frappe.get_doc("DocType", "Attendance Device")
	fieldnames = [f.fieldname for f in doc.fields]

	if "connection_mode" not in fieldnames:
		doc.append("fields", {
			"fieldname": "connection_mode",
			"fieldtype": "Select",
			"label": "Connection Mode",
			"options": "Server\nLocal Agent",
			"default": "Server",
			"insert_after": "device_type",
			"description": "Server: ERPNext connects to the device directly. Local Agent: "
							"a small agent running on the device's own network relays the "
							"connection - use this when ERPNext is remote from the device.",
		})

	if "local_agent_url" not in fieldnames:
		doc.append("fields", {
			"fieldname": "local_agent_url",
			"fieldtype": "Data",
			"label": "Local Agent URL",
			"depends_on": "eval:doc.connection_mode=='Local Agent'",
			"insert_after": "connection_mode",
			"description": "e.g. http://<agent-host>:8585 - the agent's own token is stored "
							"on this device's Attendance Device Credential (Bearer Token).",
		})

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print("Patched Attendance Device with connection_mode + local_agent_url")
