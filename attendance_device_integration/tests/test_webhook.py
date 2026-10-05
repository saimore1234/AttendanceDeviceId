"""Webhook endpoint: device auth + normalization + the same duplicate/
mapping pipeline as polled sync, without a real HTTP request (the
whitelisted function is called directly, with frappe.request mocked)."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from attendance_device_integration.api import webhook
from attendance_device_integration.tests.test_mapping_service import _ensure_device, _ensure_employee, TEST_EMPLOYEE_NUMBER

TEST_DEVICE = "_Test Webhook Device"
TOKEN = "test-webhook-token-abc123"


def _ensure_device_with_token():
	if not frappe.db.exists("Attendance Device", TEST_DEVICE):
		frappe.get_doc({
			"doctype": "Attendance Device", "device_name": TEST_DEVICE,
			"protocol_type": "ADMS", "adms_push_pull_mode": "Push", "enabled": 1,
		}).insert(ignore_permissions=True)
	if not frappe.db.exists("Attendance Device Credential", TEST_DEVICE):
		frappe.get_doc({
			"doctype": "Attendance Device Credential", "device": TEST_DEVICE, "bearer_token": TOKEN,
		}).insert(ignore_permissions=True)
	return TEST_DEVICE


class TestWebhook(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.employee = _ensure_employee()
		cls.device = _ensure_device_with_token()

	def setUp(self):
		frappe.db.delete("Attendance Raw Log", {"device": self.device})
		frappe.db.commit()

	def _call_webhook(self, payload, token=TOKEN):
		fake_request = MagicMock()
		fake_request.get_json.return_value = payload
		with patch("attendance_device_integration.api.webhook.frappe.get_request_header", return_value=f"Bearer {token}" if token else ""), \
			 patch("attendance_device_integration.api.webhook.frappe.request", fake_request):
			return webhook.device_webhook(device=self.device)

	def test_missing_token_rejected(self):
		with self.assertRaises(frappe.AuthenticationError):
			self._call_webhook({"device_user_id": TEST_EMPLOYEE_NUMBER, "punch_datetime": "2026-01-01 09:00:00"}, token=None)

	def test_wrong_token_rejected(self):
		with self.assertRaises(frappe.AuthenticationError):
			self._call_webhook({"device_user_id": TEST_EMPLOYEE_NUMBER, "punch_datetime": "2026-01-01 09:00:00"}, token="wrong-token")

	def test_valid_single_punch(self):
		result = self._call_webhook({
			"device_user_id": TEST_EMPLOYEE_NUMBER, "punch_datetime": "2026-01-02 09:00:00",
			"direction": "in", "transaction_id": "WH-1",
		})
		self.assertTrue(result["success"])
		self.assertEqual(result["inserted"], 1)
		self.assertTrue(frappe.db.exists("Attendance Raw Log", {"transaction_id": "WH-1", "source": "Webhook"}))

	def test_batch_punches(self):
		result = self._call_webhook({"punches": [
			{"device_user_id": TEST_EMPLOYEE_NUMBER, "punch_datetime": "2026-01-03 09:00:00", "transaction_id": "WH-B1"},
			{"device_user_id": TEST_EMPLOYEE_NUMBER, "punch_datetime": "2026-01-03 18:00:00", "transaction_id": "WH-B2"},
		]})
		self.assertEqual(result["inserted"], 2)

	def test_duplicate_webhook_not_double_inserted(self):
		payload = {"device_user_id": TEST_EMPLOYEE_NUMBER, "punch_datetime": "2026-01-04 09:00:00", "transaction_id": "WH-DUP"}
		r1 = self._call_webhook(payload)
		r2 = self._call_webhook(payload)
		self.assertEqual(r1["inserted"], 1)
		self.assertEqual(r2["duplicates"], 1)
