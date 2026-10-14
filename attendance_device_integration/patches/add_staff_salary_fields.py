"""Add the Employee salary fields used by the Hourly Employee Salary Report
to sites installed before they were part of the app."""

from attendance_device_integration.setup.salary_fields import ensure_salary_fields


def execute():
	ensure_salary_fields()
