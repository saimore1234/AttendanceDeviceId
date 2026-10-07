import unittest
from datetime import datetime
from unittest.mock import patch

from attendance_device_integration.utils.timezone_utils import is_valid_timezone, to_system_timezone


class TestTimezoneUtils(unittest.TestCase):
	def test_valid_timezone(self):
		self.assertTrue(is_valid_timezone("Asia/Kolkata"))
		self.assertTrue(is_valid_timezone("America/New_York"))

	def test_invalid_timezone(self):
		self.assertFalse(is_valid_timezone("Mars/Olympus_Mons"))

	@patch("attendance_device_integration.utils.timezone_utils.frappe.utils.get_system_timezone", return_value="UTC")
	def test_kolkata_to_utc_conversion(self, _mock):
		# 09:00 IST (UTC+5:30) -> 03:30 UTC
		dt = datetime(2026, 1, 1, 9, 0, 0)
		converted = to_system_timezone(dt, "Asia/Kolkata")
		self.assertEqual(converted, datetime(2026, 1, 1, 3, 30, 0))

	@patch("attendance_device_integration.utils.timezone_utils.frappe.utils.get_system_timezone", return_value="Asia/Kolkata")
	def test_same_timezone_is_identity(self, _mock):
		dt = datetime(2026, 1, 1, 9, 0, 0)
		converted = to_system_timezone(dt, "Asia/Kolkata")
		self.assertEqual(converted, dt)

	@patch("attendance_device_integration.utils.timezone_utils.frappe.utils.get_system_timezone", return_value="Asia/Calcutta")
	def test_legacy_alias_is_identity(self, _mock):
		# Asia/Calcutta (Frappe's default) and Asia/Kolkata are the same zone;
		# it must never silently fall back to UTC.
		dt = datetime(2026, 1, 1, 11, 32, 36)
		self.assertEqual(to_system_timezone(dt, "Asia/Kolkata"), dt)

	def test_invalid_device_timezone_raises(self):
		with self.assertRaises(ValueError):
			to_system_timezone(datetime(2026, 1, 1), "Not/AZone")

	def test_none_passthrough(self):
		self.assertIsNone(to_system_timezone(None, "UTC"))
