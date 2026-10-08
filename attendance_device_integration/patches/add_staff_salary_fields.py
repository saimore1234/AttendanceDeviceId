"""Employee custom fields for the Hourly Employee Salary Report: Salary Type
(Worker = paid per hour, Staff = paid a daily rate) and Daily Rate. Also
seeds Staff Full Day Hours, since a field default doesn't fill an existing
Single."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	anchor = "custom_hourly_rate" if frappe.get_meta("Employee").has_field("custom_hourly_rate") else "ctc"
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_salary_type",
					"label": "Salary Type",
					"fieldtype": "Select",
					"options": "Worker\nStaff",
					"default": "Worker",
					"insert_after": anchor,
					"description": "Worker: paid working hours x Hourly Rate. Staff: paid Daily Rate, pro-rata for short days, no pay for extra time.",
				},
				{
					"fieldname": "custom_daily_rate",
					"label": "Daily Rate",
					"fieldtype": "Currency",
					"insert_after": "custom_salary_type",
					"depends_on": "eval:doc.custom_salary_type=='Staff'",
				},
			]
		},
		update=True,
	)

	if not frappe.db.get_single_value("Attendance Integration Settings", "staff_full_day_hours"):
		frappe.db.set_single_value("Attendance Integration Settings", "staff_full_day_hours", 8)
