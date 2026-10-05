# Copyright (c) 2026, AITS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AttendanceDeviceMapping(Document):
	def validate(self):
		duplicate = frappe.db.exists("Attendance Device Mapping", {
			"device": self.device,
			"device_user_id": self.device_user_id,
			"name": ["!=", self.name],
		})
		if duplicate:
			frappe.throw(_("Device User ID {0} is already mapped for device {1} in {2}").format(
				self.device_user_id, self.device, duplicate
			))
