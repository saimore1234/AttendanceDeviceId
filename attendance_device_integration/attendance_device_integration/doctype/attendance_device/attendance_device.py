# Copyright (c) 2026, AITS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from attendance_device_integration.utils.timezone_utils import is_valid_timezone


class AttendanceDevice(Document):
	def validate(self):
		self.validate_protocol_settings()
		self.validate_timezone()

	def validate_protocol_settings(self):
		if self.protocol_type in ("Generic TCP/IP", "ESSL TCP/IP", "ZKTeco Compatible TCP/IP"):
			if not self.ip_address:
				frappe.throw(_("IP Address is required for Protocol Type {0}").format(self.protocol_type))
			if not self.port:
				frappe.throw(_("Port is required for Protocol Type {0}").format(self.protocol_type))

		elif self.protocol_type == "Generic HTTP API":
			if not self.base_url:
				frappe.throw(_("Base URL is required for Generic HTTP API"))

		elif self.protocol_type == "ADMS":
			if self.adms_push_pull_mode == "Pull" and not self.adms_attendance_endpoint:
				frappe.throw(_("Attendance Endpoint is required for ADMS Pull mode"))

		elif self.protocol_type in ("CSV Import", "Excel Import"):
			if not self.import_employee_id_column:
				frappe.throw(_("Employee/Device User ID Column is required for {0}").format(self.protocol_type))
			if not self.import_datetime_column and not (self.import_date_column and self.import_time_column):
				frappe.throw(_(
					"Configure either Combined Datetime Column, or both Date Column and Time Column"
				))

	def validate_timezone(self):
		if self.device_timezone and not is_valid_timezone(self.device_timezone):
			frappe.throw(_("{0} is not a valid IANA timezone name (e.g. Asia/Kolkata)").format(self.device_timezone))
