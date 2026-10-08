"""Hourly Employee Salary Report.

Employee Checkin IN/OUT punches -> paired working hours -> salary.

Worker: working hours x Employee hourly rate, all hours paid.
Staff: Daily Rate for a full day (Staff Full Day Hours in Attendance
Integration Settings); shorter days paid pro-rata at Daily Rate / Full Day
Hours per hour; time beyond a full day is not paid.

This is a Script Report rather than a Query Report: punches must be paired
chronologically per employee (multiple IN/OUT per day, shifts crossing
midnight, missing punches), which a single SQL statement can't do reliably.
The database does the filtering; only the pairing happens in Python.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate

HOURLY_RATE_FIELD = "custom_hourly_rate"
SALARY_TYPE_FIELD = "custom_salary_type"
DAILY_RATE_FIELD = "custom_daily_rate"

WORKER = "Worker"
STAFF = "Staff"

# An IN followed by an OUT more than this many hours later is treated as a
# missing OUT plus a missing IN, not as one very long shift.
MAX_PAIR_HOURS = 24

COMPLETE = "Complete"
MISSING_OUT = "Missing OUT"
MISSING_IN = "Missing IN"
INVALID_SEQUENCE = "Invalid Punch Sequence"

TWO_PLACES = Decimal("0.01")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	group_by = filters.group_by or "Daily"
	full_day_hours = get_staff_full_day_hours()

	employees = get_employees(filters)
	checkins = get_checkins(filters, employees) if employees else []
	days = build_daily_rows(
		checkins,
		employees,
		getdate(filters.from_date),
		getdate(filters.to_date),
		bool(filters.include_incomplete),
		full_day_hours,
	)

	data = days if group_by == "Daily" else summarise(days, group_by)
	return get_columns(group_by), [to_output(row) for row in data], None, None, get_report_summary(days)


def validate_filters(filters):
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("From Date and To Date are mandatory"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))
	meta = frappe.get_meta("Employee")
	for fieldname in (HOURLY_RATE_FIELD, SALARY_TYPE_FIELD, DAILY_RATE_FIELD):
		if not meta.has_field(fieldname):
			frappe.throw(_("Field {0} not found on Employee - run bench migrate").format(fieldname))


def get_staff_full_day_hours():
	hours = Decimal(str(frappe.db.get_single_value("Attendance Integration Settings", "staff_full_day_hours") or 0))
	if hours <= 0:
		frappe.throw(_("Set Staff Full Day Hours in Attendance Integration Settings"))
	return hours


def get_employees(filters):
	emp_filters = []
	if filters.employee:
		emp_filters.append(["name", "=", filters.employee])
	if filters.department:
		emp_filters.append(["department", "=", filters.department])
	if filters.employment_type:
		emp_filters.append(["employment_type", "=", filters.employment_type])
	if filters.salary_type == STAFF:
		emp_filters.append([SALARY_TYPE_FIELD, "=", STAFF])
	elif filters.salary_type == WORKER:
		emp_filters.append([SALARY_TYPE_FIELD, "!=", STAFF])  # blank counts as Worker

	# get_list (not get_all) so Employee read permission and User Permissions apply.
	rows = frappe.get_list(
		"Employee",
		filters=emp_filters,
		fields=[
			"name",
			"employee_name",
			"department",
			f"{HOURLY_RATE_FIELD} as hourly_rate",
			f"{SALARY_TYPE_FIELD} as salary_type",
			f"{DAILY_RATE_FIELD} as daily_rate",
		],
		limit_page_length=0,
	)
	return {row.name: row for row in rows}


def get_checkins(filters, employees):
	# One day either side so overnight pairs at the range edges are complete;
	# days outside the range are dropped after pairing.
	start = get_datetime(add_days(filters.from_date, -1))
	end = get_datetime(add_days(filters.to_date, 2))
	return frappe.get_list(
		"Employee Checkin",
		filters=[
			["employee", "in", list(employees)],
			["time", ">=", start],
			["time", "<", end],
		],
		fields=["employee", "time", "log_type"],
		order_by="employee asc, time asc",
		limit_page_length=0,
	)


def infer_missing_log_types(punches):
	"""Fill a blank log_type by position within the calendar day (1st IN,
	2nd OUT, ...) - the same rule the integration's "Sequential IN/OUT"
	pairing mode uses when creating checkins."""
	seen_per_day = defaultdict(int)
	result = []
	for p in punches:
		time = get_datetime(p.time)
		log_type = (p.log_type or "").upper()
		inferred = log_type not in ("IN", "OUT")
		if inferred:
			log_type = "IN" if seen_per_day[time.date()] % 2 == 0 else "OUT"
		seen_per_day[time.date()] += 1
		result.append(frappe._dict(time=time, log_type=log_type, inferred=inferred))
	return result


def pair_punches(punches):
	"""Pair one employee's chronological punches into IN -> OUT pairs.

	Returns (pairs, strays): pairs is [(in_punch, out_punch)], strays is
	[(punch, issue)] for punches that couldn't be paired."""
	max_seconds = MAX_PAIR_HOURS * 3600
	pairs, strays = [], []
	open_in = None

	for p in punches:
		if p.log_type == "IN":
			if open_in:
				strays.append((open_in, MISSING_OUT))
			open_in = p
		elif open_in and (p.time - open_in.time).total_seconds() <= max_seconds:
			pairs.append((open_in, p))
			open_in = None
		else:
			if open_in:
				strays.append((open_in, MISSING_OUT))
				open_in = None
			strays.append((p, MISSING_IN))

	if open_in:
		strays.append((open_in, MISSING_OUT))
	return pairs, strays


def build_daily_rows(checkins, employees, from_date, to_date, include_incomplete=False, full_day_hours=Decimal(8)):
	by_employee = defaultdict(list)
	for c in checkins:
		by_employee[c.employee].append(c)

	days = {}

	def day_for(employee, date):
		if (employee, date) not in days:
			days[(employee, date)] = frappe._dict(
				employee=employee, date=date, seconds=Decimal(0), ins=[], outs=[], issues=set(), inferred=False, punches=0
			)
		return days[(employee, date)]

	for employee, punches in by_employee.items():
		punches = infer_missing_log_types(sorted(punches, key=lambda p: get_datetime(p.time)))
		pairs, strays = pair_punches(punches)

		# A pair belongs to the day of its IN, so an overnight shift stays on one row.
		for in_p, out_p in pairs:
			day = day_for(employee, in_p.time.date())
			day.seconds += Decimal(str((out_p.time - in_p.time).total_seconds()))
			day.ins.append(in_p.time)
			day.outs.append(out_p.time)
			day.inferred = day.inferred or in_p.inferred or out_p.inferred
			day.punches += 2

		for p, issue in strays:
			day = day_for(employee, p.time.date())
			day.issues.add(issue)
			(day.ins if p.log_type == "IN" else day.outs).append(p.time)
			day.inferred = day.inferred or p.inferred
			day.punches += 1

	rows = []
	for (employee, date), day in sorted(days.items()):
		if not (from_date <= date <= to_date):
			continue
		emp = employees[employee]
		status = punch_status(day.issues)
		working_hours = (day.seconds / 3600).quantize(TWO_PLACES, ROUND_HALF_UP)
		payable_hours = working_hours if status == COMPLETE or include_incomplete else Decimal(0)

		remarks = []
		if any(t.date() > date for t in day.outs):
			remarks.append(_("Overnight"))
		if day.inferred:
			remarks.append(_("IN/OUT inferred from punch order"))
		if status != COMPLETE and not include_incomplete and working_hours:
			remarks.append(_("Not paid: incomplete punches"))

		salary_type = STAFF if emp.salary_type == STAFF else WORKER
		daily_rate = paid_days = None
		if salary_type == STAFF:
			daily_rate = to_decimal(emp.daily_rate)
			if payable_hours > full_day_hours:
				remarks.append(_("Time beyond full day not paid"))
				payable_hours = full_day_hours
			# Pro-rata per hour; a full day comes out at exactly the daily rate.
			salary = (payable_hours * daily_rate / full_day_hours).quantize(TWO_PLACES, ROUND_HALF_UP)
			hourly_rate = (daily_rate / full_day_hours).quantize(TWO_PLACES, ROUND_HALF_UP)
			paid_days = (payable_hours / full_day_hours).quantize(TWO_PLACES, ROUND_HALF_UP)
			if not daily_rate:
				remarks.append(_("No daily rate on Employee"))
		else:
			hourly_rate = to_decimal(emp.hourly_rate)
			salary = (payable_hours * hourly_rate).quantize(TWO_PLACES, ROUND_HALF_UP)
			if not hourly_rate:
				remarks.append(_("No hourly rate on Employee"))

		rows.append(frappe._dict(
			employee=employee,
			employee_name=emp.employee_name,
			department=emp.department,
			salary_type=salary_type,
			date=date,
			first_in=min(day.ins).strftime("%H:%M:%S") if day.ins else None,
			last_out=max(day.outs).strftime("%H:%M:%S") if day.outs else None,
			punch_count=day.punches,
			working_hours=working_hours,
			payable_hours=payable_hours,
			paid_days=paid_days,
			hourly_rate=hourly_rate,
			daily_rate=daily_rate,
			salary=salary,
			punch_status=status,
			remarks=", ".join(remarks),
		))
	return rows


def punch_status(issues):
	if not issues:
		return COMPLETE
	if len(issues) == 1:
		return next(iter(issues))
	return INVALID_SEQUENCE


def summarise(days, group_by):
	groups = {}
	for d in days:
		month = d.date.strftime("%Y-%m") if group_by == "Monthly" else None
		key = (d.employee, month)
		if key not in groups:
			groups[key] = frappe._dict(
				employee=d.employee, employee_name=d.employee_name, department=d.department,
				salary_type=d.salary_type, month=month, complete_days=0, incomplete_days=0,
				working_hours=Decimal(0), payable_hours=Decimal(0),
				paid_days=Decimal(0) if d.salary_type == STAFF else None,
				hourly_rate=d.hourly_rate, daily_rate=d.daily_rate, salary=Decimal(0),
			)
		g = groups[key]
		if d.punch_status == COMPLETE:
			g.complete_days += 1
		else:
			g.incomplete_days += 1
		g.working_hours += d.working_hours
		g.payable_hours += d.payable_hours
		g.salary += d.salary
		if g.salary_type == STAFF:
			g.paid_days += d.paid_days

	for g in groups.values():
		if g.salary_type == WORKER:
			# Total Salary = Total Hours x Hourly Rate, not a sum of rounded daily amounts.
			g.salary = (g.payable_hours * g.hourly_rate).quantize(TWO_PLACES, ROUND_HALF_UP)
	return sorted(groups.values(), key=lambda g: (g.employee, g.month or ""))


def get_report_summary(days):
	per_employee = summarise(days, "Employee")
	total_hours = sum((g.payable_hours for g in per_employee), Decimal(0))
	total_salary = sum((g.salary for g in per_employee), Decimal(0))
	return [
		{"label": _("Total Employees"), "value": len(per_employee), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Total Payable Hours"), "value": float(total_hours), "datatype": "Float", "indicator": "Blue"},
		{"label": _("Total Salary"), "value": float(total_salary), "datatype": "Currency", "indicator": "Green"},
	]


def get_columns(group_by):
	employee_cols = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 150},
		{"label": _("Salary Type"), "fieldname": "salary_type", "fieldtype": "Data", "width": 100},
	]
	money_cols = [
		{"label": _("Paid Days"), "fieldname": "paid_days", "fieldtype": "Float", "precision": 2, "width": 90},
		{"label": _("Hourly Rate"), "fieldname": "hourly_rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Daily Rate"), "fieldname": "daily_rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Salary"), "fieldname": "salary", "fieldtype": "Currency", "width": 120},
	]
	hours_cols = [
		{"label": _("Working Hours"), "fieldname": "working_hours", "fieldtype": "Float", "precision": 2, "width": 120},
		{"label": _("Payable Hours"), "fieldname": "payable_hours", "fieldtype": "Float", "precision": 2, "width": 120},
	]

	if group_by == "Daily":
		return (
			employee_cols
			+ [
				{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
				{"label": _("First IN"), "fieldname": "first_in", "fieldtype": "Time", "width": 90},
				{"label": _("Last OUT"), "fieldname": "last_out", "fieldtype": "Time", "width": 90},
				{"label": _("Punches"), "fieldname": "punch_count", "fieldtype": "Int", "width": 80},
			]
			+ hours_cols
			+ money_cols
			+ [
				{"label": _("Punch Status"), "fieldname": "punch_status", "fieldtype": "Data", "width": 170},
				{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 260},
			]
		)

	month_col = [{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 90}] if group_by == "Monthly" else []
	return (
		employee_cols
		+ month_col
		+ [
			{"label": _("Complete Days"), "fieldname": "complete_days", "fieldtype": "Int", "width": 120},
			{"label": _("Incomplete Days"), "fieldname": "incomplete_days", "fieldtype": "Int", "width": 120},
		]
		+ hours_cols
		+ money_cols
	)


def to_decimal(value):
	return Decimal(str(value or 0)).quantize(TWO_PLACES, ROUND_HALF_UP)


def to_output(row):
	return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}
