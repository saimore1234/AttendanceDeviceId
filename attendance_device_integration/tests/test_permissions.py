"""Role/permission checks: Integration User gets read-only access to the
operational doctypes and NO access at all to stored credentials."""

import frappe
from frappe.tests.utils import FrappeTestCase

TEST_USER_EMAIL = "adi-integration-user@example.com"


def _ensure_test_user():
	if not frappe.db.exists("User", TEST_USER_EMAIL):
		frappe.get_doc({
			"doctype": "User", "email": TEST_USER_EMAIL, "first_name": "ADI Integration User",
			"send_welcome_email": 0, "roles": [{"role": "Attendance Integration User"}],
		}).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", TEST_USER_EMAIL)
		if not any(r.role == "Attendance Integration User" for r in user.roles):
			user.append("roles", {"role": "Attendance Integration User"})
			user.save(ignore_permissions=True)
	return TEST_USER_EMAIL


class TestPermissions(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.test_user = _ensure_test_user()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_integration_user_can_read_device(self):
		frappe.set_user(self.test_user)
		self.assertTrue(frappe.has_permission("Attendance Device", "read"))

	def test_integration_user_cannot_write_device(self):
		frappe.set_user(self.test_user)
		self.assertFalse(frappe.has_permission("Attendance Device", "write"))

	def test_integration_user_cannot_delete_device(self):
		frappe.set_user(self.test_user)
		self.assertFalse(frappe.has_permission("Attendance Device", "delete"))

	def test_integration_user_has_no_credential_access_at_all(self):
		frappe.set_user(self.test_user)
		self.assertFalse(frappe.has_permission("Attendance Device Credential", "read"))
		self.assertFalse(frappe.has_permission("Attendance Device Credential", "write"))

	def test_integration_manager_can_write_device(self):
		frappe.set_user("Administrator")
		self.assertTrue(frappe.has_permission("Attendance Device", "write"))
		self.assertTrue(frappe.has_permission("Attendance Device Credential", "read"))
