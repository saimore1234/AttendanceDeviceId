import unittest
from datetime import date, datetime

import frappe

from attendance_device_integration.attendance_device_integration.report.hourly_employee_salary_report.hourly_employee_salary_report import (
	build_daily_rows,
	holiday_label,
	summarise,
	to_output,
)

EMPLOYEES = {
	"EMP-RAVI": frappe._dict(name="EMP-RAVI", employee_name="Ravi", department="Production", hourly_rate=65),
	"EMP-AMIT": frappe._dict(name="EMP-AMIT", employee_name="Amit", department="Production", hourly_rate=70),
	"EMP-STAFF": frappe._dict(name="EMP-STAFF", employee_name="Priya", department="Office", salary_type="Staff", daily_rate=800),
}


def staff_day(*punches):
	"""One Staff day on 2026-10-01, punches as (HH:MM, IN/OUT)."""
	(row,) = daily([punch("EMP-STAFF", f"2026-10-01 {t}", lt) for t, lt in punches])
	return row


class TestHolidayLabel(unittest.TestCase):
	def test_html_description_is_stripped_and_weekly_off_is_named(self):
		html = frappe._dict(description='<div class="ql-editor read-mode"><p>Janmastami</p></div>', weekly_off=0)
		self.assertEqual(holiday_label(html), "Janmastami")
		self.assertEqual(holiday_label(frappe._dict(description="Sunday", weekly_off=1)), "Weekly Off (Sunday)")
		self.assertEqual(holiday_label(frappe._dict(description=None, weekly_off=0)), "Holiday")


def holiday(label, paid=True):
	return frappe._dict(label=label, paid=paid)


def punch(employee, when, log_type):
	return frappe._dict(employee=employee, time=datetime.fromisoformat(when), log_type=log_type)


def daily(checkins, start="2026-10-01", end="2026-10-31", include_incomplete=False):
	rows = build_daily_rows(checkins, EMPLOYEES, date.fromisoformat(start), date.fromisoformat(end), include_incomplete)
	return [to_output(r) for r in rows]


class TestHourlySalaryReport(unittest.TestCase):
	def test_staff_paid_full_day_for_holiday_without_punches(self):
		rows = build_daily_rows(
			[], EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31),
			holidays={"EMP-STAFF": {
				date(2026, 10, 2): holiday("Gandhi Jayanti"),
				date(2026, 11, 1): holiday("Outside the range"),
			}},
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual(row["date"], date(2026, 10, 2))
		self.assertEqual(row["holiday"], "Gandhi Jayanti")
		self.assertEqual(row["punch_status"], "Paid Holiday")
		self.assertEqual(row["salary"], 800.0)
		self.assertEqual(row["paid_days"], 1.0)
		self.assertEqual(row["working_hours"], 0.0)

	def test_staff_who_works_a_holiday_is_paid_one_day_not_pro_rata(self):
		rows = build_daily_rows(
			[punch("EMP-STAFF", "2026-10-02 09:00", "IN"), punch("EMP-STAFF", "2026-10-02 12:00", "OUT")],
			EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31),
			holidays={"EMP-STAFF": {date(2026, 10, 2): holiday("Gandhi Jayanti")}},
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual(row["salary"], 800.0)
		self.assertEqual(row["working_hours"], 3.0)
		self.assertIn("Worked on holiday", row["remarks"])

	def test_holiday_counts_as_complete_day_in_monthly_summary(self):
		days = build_daily_rows(
			[], EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31),
			holidays={"EMP-STAFF": {date(2026, 10, 2): holiday("Gandhi Jayanti")}},
		)
		(summary,) = summarise(days, "Employee")
		self.assertEqual((summary.complete_days, summary.incomplete_days), (1, 0))

	def test_worker_sees_unpaid_holiday_row(self):
		rows = build_daily_rows(
			[], EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31),
			holidays={"EMP-RAVI": {date(2026, 10, 2): holiday("Gandhi Jayanti", paid=False)}},
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual((row["holiday"], row["punch_status"], row["salary"]), ("Gandhi Jayanti", "Holiday", 0.0))
		self.assertIn("not paid", row["remarks"])
		(summary,) = summarise(rows, "Employee")
		self.assertEqual((summary.complete_days, summary.incomplete_days), (0, 0))

	def test_worker_who_works_a_holiday_is_paid_for_hours_and_row_names_the_holiday(self):
		rows = build_daily_rows(
			[punch("EMP-RAVI", "2026-10-02 09:00", "IN"), punch("EMP-RAVI", "2026-10-02 17:00", "OUT")],
			EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31),
			holidays={"EMP-RAVI": {date(2026, 10, 2): holiday("Gandhi Jayanti", paid=False)}},
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual((row["holiday"], row["salary"]), ("Gandhi Jayanti", 520.0))
		self.assertIn("Worked on holiday", row["remarks"])

	def test_stray_out_just_before_the_real_in_does_not_make_the_day_unpaid(self):
		punches = [
			punch("EMP-RAVI", "2026-10-14 09:00:20", "OUT"),
			punch("EMP-RAVI", "2026-10-14 09:00:53", "IN"),
			punch("EMP-RAVI", "2026-10-14 18:28:56", "OUT"),
		]
		(stock,) = daily(punches)
		self.assertEqual(stock["punch_status"], "Missing IN")

		rows = build_daily_rows(
			punches, EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31), duplicate_window_minutes=5
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual(row["punch_status"], "Complete")
		self.assertEqual((row["first_in"], row["last_out"]), ("09:00:53", "18:28:56"))
		self.assertEqual(row["working_hours"], 9.47)
		self.assertIn("Repeated scans merged", row["remarks"])

	def test_double_scan_out_keeps_the_latest_and_in_keeps_the_earliest(self):
		rows = build_daily_rows(
			[
				punch("EMP-RAVI", "2026-10-15 09:00:00", "IN"),
				punch("EMP-RAVI", "2026-10-15 09:00:40", "IN"),
				punch("EMP-RAVI", "2026-10-15 18:00:00", "OUT"),
				punch("EMP-RAVI", "2026-10-15 18:00:30", "OUT"),
			],
			EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31), duplicate_window_minutes=5,
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual(row["punch_status"], "Complete")
		self.assertEqual((row["first_in"], row["last_out"]), ("09:00:00", "18:00:30"))

	def test_genuine_break_out_in_is_not_merged(self):
		rows = build_daily_rows(
			[
				punch("EMP-RAVI", "2026-10-15 09:00", "IN"),
				punch("EMP-RAVI", "2026-10-15 13:00", "OUT"),
				punch("EMP-RAVI", "2026-10-15 13:30", "IN"),
				punch("EMP-RAVI", "2026-10-15 18:00", "OUT"),
			],
			EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31), duplicate_window_minutes=5,
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual(row["working_hours"], 8.5)
		self.assertNotIn("merged", row["remarks"])

	def test_machine_sending_only_out_is_paired_by_order(self):
		punches = [
			punch("EMP-RAVI", "2026-10-05 09:00", "OUT"),
			punch("EMP-RAVI", "2026-10-05 18:00", "OUT"),
		]
		(stock,) = daily(punches)
		self.assertEqual(stock["punch_status"], "Missing IN")

		rows = build_daily_rows(
			punches, EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31), ignore_log_type=True
		)
		(row,) = [to_output(r) for r in rows]
		self.assertEqual(row["punch_status"], "Complete")
		self.assertEqual(row["working_hours"], 9.0)
		self.assertEqual((row["first_in"], row["last_out"]), ("09:00:00", "18:00:00"))
		self.assertIn("inferred", row["remarks"])

	def test_break_is_excluded(self):
		(row,) = daily([
			punch("EMP-RAVI", "2026-10-01 09:00", "IN"),
			punch("EMP-RAVI", "2026-10-01 13:00", "OUT"),
			punch("EMP-RAVI", "2026-10-01 14:00", "IN"),
			punch("EMP-RAVI", "2026-10-01 18:00", "OUT"),
		])
		self.assertEqual(row["working_hours"], 8.0)
		self.assertEqual(row["hourly_rate"], 65.0)
		self.assertEqual(row["salary"], 520.0)
		self.assertEqual(row["punch_status"], "Complete")
		self.assertEqual((row["first_in"], row["last_out"]), ("09:00:00", "18:00:00"))

	def test_single_pair_no_break_rule(self):
		(row,) = daily([
			punch("EMP-RAVI", "2026-10-02 09:00", "IN"),
			punch("EMP-RAVI", "2026-10-02 18:00", "OUT"),
		])
		self.assertEqual(row["working_hours"], 9.0)
		self.assertEqual(row["salary"], 585.0)

	def test_missing_out_is_not_paid(self):
		(row,) = daily([punch("EMP-RAVI", "2026-10-03 09:00", "IN")])
		self.assertEqual(row["punch_status"], "Missing OUT")
		self.assertEqual(row["working_hours"], 0.0)
		self.assertEqual(row["salary"], 0.0)

	def test_missing_in(self):
		(row,) = daily([punch("EMP-RAVI", "2026-10-03 18:00", "OUT")])
		self.assertEqual(row["punch_status"], "Missing IN")
		self.assertEqual(row["salary"], 0.0)

	def test_partial_day_paid_only_when_configured(self):
		punches = [
			punch("EMP-RAVI", "2026-10-04 09:00", "IN"),
			punch("EMP-RAVI", "2026-10-04 13:00", "OUT"),
			punch("EMP-RAVI", "2026-10-04 14:00", "IN"),
		]
		(row,) = daily(punches)
		self.assertEqual((row["punch_status"], row["working_hours"], row["payable_hours"], row["salary"]),
						 ("Missing OUT", 4.0, 0.0, 0.0))
		(row,) = daily(punches, include_incomplete=True)
		self.assertEqual((row["payable_hours"], row["salary"]), (4.0, 260.0))

	def test_both_issues_is_invalid_sequence(self):
		(row,) = daily([
			punch("EMP-RAVI", "2026-10-05 08:00", "OUT"),
			punch("EMP-RAVI", "2026-10-05 09:00", "IN"),
		])
		self.assertEqual(row["punch_status"], "Invalid Punch Sequence")

	def test_overnight_shift(self):
		(row,) = daily([
			punch("EMP-RAVI", "2026-10-06 22:00", "IN"),
			punch("EMP-RAVI", "2026-10-07 06:00", "OUT"),
		])
		self.assertEqual(row["date"], date(2026, 10, 6))
		self.assertEqual(row["working_hours"], 8.0)
		self.assertEqual(row["punch_status"], "Complete")
		self.assertIn("Overnight", row["remarks"])

	def test_pair_longer_than_24h_is_not_paired(self):
		rows = daily([
			punch("EMP-RAVI", "2026-10-08 09:00", "IN"),
			punch("EMP-RAVI", "2026-10-09 18:00", "OUT"),
		])
		self.assertEqual([r["punch_status"] for r in rows], ["Missing OUT", "Missing IN"])

	def test_rounding(self):
		(row,) = daily([
			punch("EMP-RAVI", "2026-10-10 09:00", "IN"),
			punch("EMP-RAVI", "2026-10-10 16:30", "OUT"),
		])
		self.assertEqual((row["working_hours"], row["salary"]), (7.5, 487.5))

	def test_blank_log_type_inferred_by_order(self):
		(row,) = daily([
			punch("EMP-RAVI", "2026-10-11 09:00", ""),
			punch("EMP-RAVI", "2026-10-11 17:00", None),
		])
		self.assertEqual((row["working_hours"], row["punch_status"]), (8.0, "Complete"))
		self.assertIn("inferred", row["remarks"])

	def test_rows_outside_range_dropped(self):
		rows = daily([
			punch("EMP-RAVI", "2026-09-30 22:00", "IN"),
			punch("EMP-RAVI", "2026-10-01 06:00", "OUT"),
		])
		self.assertEqual(rows, [])

	def test_per_employee_rates_and_monthly_summary(self):
		days = build_daily_rows([
			punch("EMP-RAVI", "2026-10-01 09:00", "IN"),
			punch("EMP-RAVI", "2026-10-01 17:00", "OUT"),
			punch("EMP-RAVI", "2026-10-02 09:00", "IN"),
			punch("EMP-AMIT", "2026-10-01 09:00", "IN"),
			punch("EMP-AMIT", "2026-10-01 17:00", "OUT"),
		], EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31))
		summary = {g.employee: to_output(g) for g in summarise(days, "Monthly")}
		self.assertEqual(summary["EMP-RAVI"]["salary"], 520.0)
		self.assertEqual(summary["EMP-RAVI"]["incomplete_days"], 1)
		self.assertEqual(summary["EMP-AMIT"]["salary"], 560.0)
		self.assertEqual(summary["EMP-AMIT"]["month"], "2026-10")


class TestStaffDailySalary(unittest.TestCase):
	# Daily Rate 800, Staff Full Day Hours 8 (shift 9:00-5:30 minus 30 min lunch)

	def test_full_shift_with_lunch_is_full_day(self):
		row = staff_day(("09:00", "IN"), ("13:00", "OUT"), ("13:30", "IN"), ("17:30", "OUT"))
		self.assertEqual((row["working_hours"], row["paid_days"], row["salary"]), (8.0, 1.0, 800.0))
		self.assertEqual((row["salary_type"], row["hourly_rate"], row["daily_rate"]), ("Staff", 100.0, 800.0))

	def test_extra_time_not_paid(self):
		row = staff_day(("09:00", "IN"), ("13:00", "OUT"), ("13:30", "IN"), ("19:30", "OUT"))
		self.assertEqual((row["working_hours"], row["payable_hours"], row["salary"]), (10.0, 8.0, 800.0))
		self.assertIn("beyond full day", row["remarks"])

	def test_leaving_at_1pm_is_half_day(self):
		row = staff_day(("09:00", "IN"), ("13:00", "OUT"))
		self.assertEqual((row["working_hours"], row["paid_days"], row["salary"]), (4.0, 0.5, 400.0))

	def test_short_days_paid_hourly(self):
		self.assertEqual(staff_day(("09:00", "IN"), ("15:00", "OUT"))["salary"], 600.0)
		self.assertEqual(staff_day(("09:00", "IN"), ("16:00", "OUT"))["salary"], 700.0)
		self.assertEqual(staff_day(("09:00", "IN"), ("16:15", "OUT"))["salary"], 725.0)

	def test_staff_missing_out_not_paid(self):
		row = staff_day(("09:00", "IN"))
		self.assertEqual((row["punch_status"], row["paid_days"], row["salary"]), ("Missing OUT", 0.0, 0.0))

	def test_staff_monthly_summary(self):
		days = build_daily_rows([
			punch("EMP-STAFF", "2026-10-01 09:00", "IN"),
			punch("EMP-STAFF", "2026-10-01 18:00", "OUT"),  # 9h -> capped, 800
			punch("EMP-STAFF", "2026-10-02 09:00", "IN"),
			punch("EMP-STAFF", "2026-10-02 13:00", "OUT"),  # 4h -> 400
			punch("EMP-STAFF", "2026-10-03 09:00", "IN"),
			punch("EMP-STAFF", "2026-10-03 15:00", "OUT"),  # 6h -> 600
		], EMPLOYEES, date(2026, 10, 1), date(2026, 10, 31))
		(g,) = [to_output(g) for g in summarise(days, "Employee")]
		self.assertEqual((g["working_hours"], g["payable_hours"], g["paid_days"], g["salary"]), (19.0, 18.0, 2.25, 1800.0))
