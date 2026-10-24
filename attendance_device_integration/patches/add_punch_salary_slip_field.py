"""Add the Punch-Based Pay field to Salary Slip on sites installed before it existed."""

from attendance_device_integration.setup.salary_fields import ensure_salary_fields


def execute():
	ensure_salary_fields()
