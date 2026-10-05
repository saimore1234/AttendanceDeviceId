"""Creates Number Cards (dashboard KPIs) and the Attendance Device
Integration Workspace that surfaces them alongside shortcuts to every
doctype and report.

NOTE: Number Card auto-names from its `label` field (not from any "name"
key passed in) - so label IS the canonical identifier used everywhere
below, including in the Workspace's number_cards child table.
"""

import json

import frappe

MODULE = "Attendance Device Integration"


def make_number_card(label, doctype, function="Count", filters=None, color="blue"):
	if frappe.db.exists("Number Card", label):
		return label
	frappe.get_doc({
		"doctype": "Number Card",
		"label": label,
		"document_type": doctype,
		"function": function,
		"filters_json": json.dumps(filters or []),
		"is_public": 1,
		"show_percentage_stats": 0,
		"color": color,
	}).insert(ignore_permissions=True)
	return label


def make_cards():
	make_number_card("Total Devices", "Attendance Device", color="blue")
	make_number_card("Enabled Devices", "Attendance Device",
					  filters=[["Attendance Device", "enabled", "=", 1]], color="green")
	make_number_card("Devices With Errors", "Attendance Device",
					  filters=[["Attendance Device", "last_sync_status", "in", ["Failed", "Offline"]]], color="red")
	make_number_card("Today's Punches", "Attendance Raw Log",
					  filters=[["Attendance Raw Log", "punch_date", "=", "Today"]], color="green")
	make_number_card("Unprocessed Logs", "Attendance Raw Log",
					  filters=[["Attendance Raw Log", "processing_status", "=", "Pending"]], color="orange")
	make_number_card("Unmapped Employees", "Attendance Raw Log",
					  filters=[["Attendance Raw Log", "processing_status", "=", "Unmapped Employee"]], color="orange")
	make_number_card("Failed Logs", "Attendance Raw Log",
					  filters=[["Attendance Raw Log", "processing_status", "=", "Error"]], color="red")
	make_number_card("Employees Mapped", "Attendance Device Mapping",
					  filters=[["Attendance Device Mapping", "active", "=", 1]], color="blue")


def execute():
	frappe.set_user("Administrator")
	make_cards()
	frappe.db.commit()

	if frappe.db.exists("Workspace", "Attendance Device Integration"):
		print("Workspace already exists, skipping")
		return

	shortcuts = [
		{"label": "Attendance Device", "type": "DocType", "link_to": "Attendance Device", "color": "Blue"},
		{"label": "Attendance Device Mapping", "type": "DocType", "link_to": "Attendance Device Mapping", "color": "Green"},
		{"label": "Attendance Raw Log", "type": "DocType", "link_to": "Attendance Raw Log", "color": "Orange"},
		{"label": "Attendance Sync Log", "type": "DocType", "link_to": "Attendance Sync Log", "color": "Orange"},
		{"label": "Attendance Device Command Log", "type": "DocType", "link_to": "Attendance Device Command Log", "color": "Grey"},
		{"label": "Attendance Integration Settings", "type": "DocType", "link_to": "Attendance Integration Settings", "color": "Red"},
	]

	cards = [
		"Total Devices", "Enabled Devices", "Devices With Errors", "Today's Punches",
		"Unprocessed Logs", "Unmapped Employees", "Failed Logs", "Employees Mapped",
	]

	content_blocks = [
		{"id": "header", "type": "header", "data": {"text": "<span class=\"h4\"><b>Attendance Device Integration</b></span>", "col": 12}},
		{"id": "card_section_header", "type": "card", "data": {"card_name": "Quick Access", "col": 12}},
		{"id": "shortcuts_spacer", "type": "spacer", "data": {"col": 12}},
	]
	for i, c in enumerate(cards):
		content_blocks.append({"id": f"card_{i}", "type": "number_card", "data": {"number_card_name": c, "col": 3}})
	for i, s in enumerate(shortcuts):
		content_blocks.append({"id": f"shortcut_{i}", "type": "shortcut", "data": {"shortcut_name": s["label"], "col": 3}})

	doc = frappe.get_doc({
		"doctype": "Workspace",
		"name": "Attendance Device Integration",
		"title": "Attendance Device Integration",
		"label": "Attendance Device Integration",
		"module": MODULE,
		"public": 1,
		"is_hidden": 0,
		"icon": "fingerprint" if frappe.db.exists("DocType", "DocType") else "form",
		"content": json.dumps(content_blocks),
		"shortcuts": shortcuts,
		"number_cards": [{"number_card_name": c} for c in cards],
		"roles": [{"role": "Attendance Integration Manager"}, {"role": "Attendance Integration User"}, {"role": "System Manager"}],
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print("Created Workspace: Attendance Device Integration")
