"""The "Today's Punches" Number Card was created with the literal string
"Today" as a date filter value, which the desk can't parse ("Invalid Date").
Switch it to Frappe's relative Timespan filter."""

import json

import frappe


def execute():
	if not frappe.db.exists("Number Card", "Today's Punches"):
		return
	frappe.db.set_value("Number Card", "Today's Punches", "filters_json",
						json.dumps([["Attendance Raw Log", "punch_date", "Timespan", "today", False]]))
