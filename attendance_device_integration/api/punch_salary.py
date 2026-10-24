"""Create Salary Slips from the Hourly Employee Salary Report.

preview() lists who would get a slip and for how much; create_slips() creates
draft slips (never submitted). Both run the report with the same filters the
user is looking at, grouped per employee, so the amounts match the screen.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from attendance_device_integration.attendance_device_integration.report.hourly_employee_salary_report import (
	hourly_employee_salary_report as report,
)


def _get_rows(filters) -> tuple:
	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters)
	filters.group_by = "Employee"  # one slip per employee for the whole period
	_columns, data, *_rest = report.execute(filters)
	return filters, data


def _existing_slip(employee, from_date, to_date):
	return frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "start_date": from_date, "end_date": to_date, "docstatus": ["!=", 2]},
		"name",
	)


@frappe.whitelist()
def preview(filters):
	frappe.has_permission("Salary Slip", "create", throw=True)
	filters, data = _get_rows(filters)

	rows = []
	for row in data:
		amount = flt(row.get("salary"))
		existing = _existing_slip(row["employee"], filters.from_date, filters.to_date)
		if existing:
			state = _("Slip exists: {0}").format(existing)
		elif amount <= 0:
			state = _("No pay for this period")
		elif row.get("incomplete_days"):
			state = _("Ready ({0} incomplete days)").format(row["incomplete_days"])
		else:
			state = _("Ready")
		rows.append({
			"employee": row["employee"],
			"employee_name": row.get("employee_name"),
			"payable_hours": row.get("payable_hours"),
			"salary": amount,
			"incomplete_days": row.get("incomplete_days") or 0,
			"will_create": 0 if existing or amount <= 0 else 1,
			"state": state,
		})
	return rows


@frappe.whitelist()
def create_slips(filters, employees=None):
	"""Create a draft Salary Slip for each employee that has pay and no slip yet.
	`employees` (JSON list) limits it to the rows the user kept ticked."""
	frappe.has_permission("Salary Slip", "create", throw=True)
	filters, data = _get_rows(filters)
	wanted = set(json.loads(employees)) if isinstance(employees, str) else set(employees or [])

	result = {"created": [], "skipped": [], "failed": []}
	for row in data:
		employee = row["employee"]
		if wanted and employee not in wanted:
			continue
		amount = flt(row.get("salary"))
		if amount <= 0:
			result["skipped"].append({"employee": employee, "reason": _("No pay for this period")})
			continue
		existing = _existing_slip(employee, filters.from_date, filters.to_date)
		if existing:
			result["skipped"].append({"employee": employee, "reason": _("Slip exists: {0}").format(existing)})
			continue

		try:
			slip = _make_slip(employee, filters.from_date, filters.to_date, amount)
			result["created"].append({"employee": employee, "slip": slip.name, "gross_pay": slip.gross_pay, "net_pay": slip.net_pay})
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title=f"Punch salary slip failed for {employee}")
			result["failed"].append({"employee": employee, "reason": str(e)})
		else:
			frappe.db.commit()
	return result


def _make_slip(employee, from_date, to_date, amount):
	emp = frappe.get_cached_doc("Employee", employee)
	slip = frappe.get_doc({
		"doctype": "Salary Slip",
		"employee": employee,
		"employee_name": emp.employee_name,
		"company": emp.company,
		"posting_date": min(getdate(nowdate()), getdate(to_date)),
		"start_date": getdate(from_date),
		"end_date": getdate(to_date),
		"custom_punch_based_pay": amount,
	})
	# validate() pulls the structure's earnings/deductions, then PunchSalarySlip
	# runs the formulas on the punch-based amount.
	slip.insert()
	return slip
