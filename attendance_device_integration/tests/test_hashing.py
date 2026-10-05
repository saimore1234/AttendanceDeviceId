import unittest
from datetime import datetime

from attendance_device_integration.utils.hashing import compute_unique_hash


class TestHashing(unittest.TestCase):
	def test_deterministic(self):
		dt = datetime(2026, 1, 1, 9, 0, 0)
		h1 = compute_unique_hash("DEV-1", "101", dt, "T1")
		h2 = compute_unique_hash("DEV-1", "101", dt, "T1")
		self.assertEqual(h1, h2)

	def test_different_device_differs(self):
		dt = datetime(2026, 1, 1, 9, 0, 0)
		self.assertNotEqual(
			compute_unique_hash("DEV-1", "101", dt),
			compute_unique_hash("DEV-2", "101", dt),
		)

	def test_different_time_differs(self):
		self.assertNotEqual(
			compute_unique_hash("DEV-1", "101", datetime(2026, 1, 1, 9, 0, 0)),
			compute_unique_hash("DEV-1", "101", datetime(2026, 1, 1, 9, 0, 1)),
		)

	def test_missing_transaction_id_still_deterministic(self):
		dt = datetime(2026, 1, 1, 9, 0, 0)
		self.assertEqual(
			compute_unique_hash("DEV-1", "101", dt, None),
			compute_unique_hash("DEV-1", "101", dt, None),
		)
