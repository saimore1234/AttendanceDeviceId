import frappe
from frappe.tests.utils import FrappeTestCase

from attendance_device_integration.services import mapping_service

TEST_DEVICE = "_Test Attendance Device"
TEST_EMPLOYEE_NUMBER = "ADI-TEST-EMP-001"


def _ensure_employee():
	existing = frappe.db.get_value("Employee", {"employee_number": TEST_EMPLOYEE_NUMBER}, "name")
	if existing:
		return existing
	emp = frappe.get_doc({
		"doctype": "Employee",
		"first_name": "ADI Test Employee",
		"employee_number": TEST_EMPLOYEE_NUMBER,
		"company": "_Test Company",
		"gender": "Other",
		"date_of_birth": "1990-01-01",
		"date_of_joining": "2020-01-01",
		"status": "Active",
	}).insert(ignore_permissions=True, ignore_mandatory=True)
	return emp.name


def _ensure_device(protocol_type="Manual Entry"):
	if frappe.db.exists("Attendance Device", TEST_DEVICE):
		return TEST_DEVICE
	frappe.get_doc({
		"doctype": "Attendance Device",
		"device_name": TEST_DEVICE,
		"protocol_type": protocol_type,
		"enabled": 1,
	}).insert(ignore_permissions=True)
	return TEST_DEVICE


class TestMappingService(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.employee = _ensure_employee()
		cls.device = _ensure_device()

	def setUp(self):
		settings = frappe.get_single("Attendance Integration Settings")
		settings.auto_match_rule = "Employee Number"
		settings.save(ignore_permissions=True)
		frappe.db.delete("Attendance Device Mapping", {"device": self.device})

	def test_auto_match_by_employee_number(self):
		result = mapping_service.resolve_employee(self.device, TEST_EMPLOYEE_NUMBER)
		self.assertEqual(result, self.employee)

	def test_no_match_returns_none(self):
		result = mapping_service.resolve_employee(self.device, "NONEXISTENT-999")
		self.assertIsNone(result)

	def test_explicit_mapping_overrides_auto_match(self):
		other_employee = _ensure_employee()  # same employee here, but prove explicit path is used
		frappe.get_doc({
			"doctype": "Attendance Device Mapping",
			"device": self.device,
			"device_user_id": "DEVICE-UID-42",
			"employee": other_employee,
			"active": 1,
		}).insert(ignore_permissions=True)

		result = mapping_service.resolve_employee(self.device, "DEVICE-UID-42")
		self.assertEqual(result, other_employee)

	def test_inactive_mapping_is_ignored(self):
		frappe.get_doc({
			"doctype": "Attendance Device Mapping",
			"device": self.device,
			"device_user_id": "DEVICE-UID-99",
			"employee": self.employee,
			"active": 0,
		}).insert(ignore_permissions=True)

		result = mapping_service.resolve_employee(self.device, "DEVICE-UID-99")
		self.assertIsNone(result)

	def test_attendance_device_id_rule(self):
		"""The standard HRMS Employee field (Attendance & Leaves tab,
		fieldname attendance_device_id) - the default auto-match rule."""
		settings = frappe.get_single("Attendance Integration Settings")
		settings.auto_match_rule = "Attendance Device ID (Employee field)"
		settings.save(ignore_permissions=True)

		frappe.db.set_value("Employee", self.employee, "attendance_device_id", "X990-UID-501")

		result = mapping_service.resolve_employee(self.device, "X990-UID-501")
		self.assertEqual(result, self.employee)

		frappe.db.set_value("Employee", self.employee, "attendance_device_id", None)

	def test_employee_id_rule(self):
		settings = frappe.get_single("Attendance Integration Settings")
		settings.auto_match_rule = "Employee ID"
		settings.save(ignore_permissions=True)

		result = mapping_service.resolve_employee(self.device, self.employee)
		self.assertEqual(result, self.employee)
