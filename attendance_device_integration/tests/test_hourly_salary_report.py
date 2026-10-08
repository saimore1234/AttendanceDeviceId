import unittest
from datetime import date, datetime

import frappe

from attendance_device_integration.attendance_device_integration.report.hourly_employee_salary_report.hourly_employee_salary_report import (
	build_daily_rows,
	summarise,
	to_output,
)

EMPLOYEES = {
	"EMP-RAVI": frappe._dict(name="EMP-RAVI", employee_name="Ravi", department="Production", hourly_rate=65),
	"EMP-AMIT": frappe._dict(name="EMP-AMIT", employee_name="Amit", department="Production", hourly_rate=70),
}


def punch(employee, when, log_type):
	return frappe._dict(employee=employee, time=datetime.fromisoformat(when), log_type=log_type)


def daily(checkins, start="2026-10-01", end="2026-10-31", include_incomplete=False):
	rows = build_daily_rows(checkins, EMPLOYEES, date.fromisoformat(start), date.fromisoformat(end), include_incomplete)
	return [to_output(r) for r in rows]


class TestHourlySalaryReport(unittest.TestCase):
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
