"""Salary Slip whose pay comes from the Hourly Employee Salary Report.

Slips created from the report carry the period's punch-based pay in
custom_punch_based_pay. The employee's Salary Structure still produces the
components and deductions, but its formulas run on that amount instead of the
Salary Structure Assignment's fixed monthly base, and nothing is prorated by
payment days - the punches already decide how much was worked.

Slips without custom_punch_based_pay behave exactly as stock HRMS.
"""

from frappe.utils import date_diff, flt

from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip


class PunchSalarySlip(SalarySlip):
	def set_salary_structure_assignment(self):
		super().set_salary_structure_assignment()
		# validate() calls this on every save, so a later edit of the draft
		# keeps the punch-based amount instead of reverting to the fixed base.
		if flt(self.get("custom_punch_based_pay")):
			self._salary_structure_assignment.base = flt(self.custom_punch_based_pay)

	def get_working_days_details(self, lwp=None, for_preview=0):
		if not flt(self.get("custom_punch_based_pay")):
			return super().get_working_days_details(lwp=lwp, for_preview=for_preview)

		self.total_working_days = date_diff(self.end_date, self.start_date) + 1
		self.payment_days = self.total_working_days
		self.leave_without_pay = 0
		self.absent_days = 0
