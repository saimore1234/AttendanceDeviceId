"""Full sync_service.sync_device() flow, with the device adapter mocked
out (no physical hardware) but everything else (DocTypes, mapping,
duplicate detection, Employee Checkin creation) real."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from attendance_device_integration.device_adapters.base import RawPunch
from attendance_device_integration.services import sync_service
from attendance_device_integration.tests.test_mapping_service import _ensure_device, _ensure_employee, TEST_EMPLOYEE_NUMBER


def _fake_adapter(punches):
	adapter = MagicMock()
	adapter.get_attendance_logs_since_last_sync.return_value = punches
	adapter.get_attendance_logs_by_date.return_value = punches
	return adapter


class TestSyncService(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.employee = _ensure_employee()

	def setUp(self):
		self.device = _ensure_device()
		frappe.db.set_value("Attendance Device", self.device, "last_sync_datetime", None)
		settings = frappe.get_single("Attendance Integration Settings")
		settings.auto_match_rule = "Employee Number"
		settings.create_employee_checkin = 1
		settings.batch_size = 500
		settings.save(ignore_permissions=True)
		frappe.db.delete("Attendance Raw Log", {"device": self.device})
		frappe.db.delete("Employee Checkin", {"employee": self.employee})
		frappe.db.commit()

	@patch("attendance_device_integration.services.sync_service.get_adapter_for_device")
	def test_mapped_punch_creates_raw_log_and_checkin(self, mock_get_adapter):
		punch = RawPunch(
			device_user_id=TEST_EMPLOYEE_NUMBER, punch_datetime=datetime(2026, 1, 5, 9, 0, 0),
			direction="IN", transaction_id="SYNC-T1", raw="raw-1",
		)
		mock_get_adapter.return_value = _fake_adapter([punch])

		result = sync_service.sync_device(self.device, sync_type="Manual")

		self.assertTrue(result["success"])
		self.assertEqual(result["inserted"], 1)
		self.assertEqual(result["processed"], 1)

		raw_log = frappe.get_all("Attendance Raw Log", filters={"device": self.device, "transaction_id": "SYNC-T1"})
		self.assertEqual(len(raw_log), 1)
		raw_log_doc = frappe.get_doc("Attendance Raw Log", raw_log[0].name)
		self.assertEqual(raw_log_doc.processing_status, "Processed")
		self.assertTrue(raw_log_doc.employee_checkin)
		self.assertTrue(frappe.db.exists("Employee Checkin", raw_log_doc.employee_checkin))

	@patch("attendance_device_integration.services.sync_service.get_adapter_for_device")
	def test_duplicate_punch_not_inserted_twice(self, mock_get_adapter):
		punch = RawPunch(
			device_user_id=TEST_EMPLOYEE_NUMBER, punch_datetime=datetime(2026, 1, 5, 10, 0, 0),
			direction="IN", transaction_id="SYNC-DUP1", raw="raw-dup",
		)
		mock_get_adapter.return_value = _fake_adapter([punch])

		result1 = sync_service.sync_device(self.device, sync_type="Manual")
		result2 = sync_service.sync_device(self.device, sync_type="Manual")

		self.assertEqual(result1["inserted"], 1)
		self.assertEqual(result2["inserted"], 0)
		self.assertEqual(result2["duplicated"], 1)

		count = frappe.db.count("Attendance Raw Log", {"device": self.device, "transaction_id": "SYNC-DUP1"})
		self.assertEqual(count, 1)

	@patch("attendance_device_integration.services.sync_service.get_adapter_for_device")
	def test_unmapped_employee_logged_not_dropped(self, mock_get_adapter):
		punch = RawPunch(
			device_user_id="TOTALLY-UNKNOWN-999", punch_datetime=datetime(2026, 1, 5, 11, 0, 0),
			direction="IN", transaction_id="SYNC-UNMAPPED", raw="raw-unmapped",
		)
		mock_get_adapter.return_value = _fake_adapter([punch])

		result = sync_service.sync_device(self.device, sync_type="Manual")

		self.assertEqual(result["inserted"], 1)
		raw_log = frappe.get_all("Attendance Raw Log", filters={"transaction_id": "SYNC-UNMAPPED"},
								  fields=["name", "processing_status", "employee_checkin"])
		self.assertEqual(raw_log[0].processing_status, "Unmapped Employee")
		self.assertFalse(raw_log[0].employee_checkin)

	@patch("attendance_device_integration.services.sync_service.get_adapter_for_device")
	def test_multiple_punches_same_day_all_kept(self, mock_get_adapter):
		base = datetime(2026, 1, 6)
		punches = [
			RawPunch(device_user_id=TEST_EMPLOYEE_NUMBER, punch_datetime=base.replace(hour=9), direction="IN", transaction_id="M1", raw="r1"),
			RawPunch(device_user_id=TEST_EMPLOYEE_NUMBER, punch_datetime=base.replace(hour=13), direction="OUT", transaction_id="M2", raw="r2"),
			RawPunch(device_user_id=TEST_EMPLOYEE_NUMBER, punch_datetime=base.replace(hour=14), direction="IN", transaction_id="M3", raw="r3"),
			RawPunch(device_user_id=TEST_EMPLOYEE_NUMBER, punch_datetime=base.replace(hour=18, minute=30), direction="OUT", transaction_id="M4", raw="r4"),
		]
		mock_get_adapter.return_value = _fake_adapter(punches)

		result = sync_service.sync_device(self.device, sync_type="Manual")

		self.assertEqual(result["inserted"], 4)
		self.assertEqual(result["processed"], 4)

	@patch("attendance_device_integration.services.sync_service.get_adapter_for_device")
	def test_device_offline_does_not_raise(self, mock_get_adapter):
		from attendance_device_integration.device_adapters.base import AdapterError

		adapter = MagicMock()
		adapter.connect.side_effect = AdapterError("Connection timed out", error_code="CONNECTION_TIMEOUT")
		mock_get_adapter.return_value = adapter

		result = sync_service.sync_device(self.device, sync_type="Manual")

		self.assertFalse(result["success"])
		self.assertEqual(result["error_code"], "CONNECTION_TIMEOUT")
		# Device status reflects offline, nothing crashed
		self.assertEqual(frappe.db.get_value("Attendance Device", self.device, "last_sync_status"), "Offline")

	def test_disabled_device_sync_rejected(self):
		frappe.db.set_value("Attendance Device", self.device, "enabled", 0)
		result = sync_service.sync_device(self.device, sync_type="Manual")
		self.assertFalse(result["success"])
		frappe.db.set_value("Attendance Device", self.device, "enabled", 1)

	def test_nonexistent_device_rejected(self):
		result = sync_service.sync_device("DEVICE-DOES-NOT-EXIST", sync_type="Manual")
		self.assertFalse(result["success"])
