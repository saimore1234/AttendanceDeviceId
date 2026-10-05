"""Adapter tests - all hardware mocked out, no physical device required."""

import csv
import io
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from attendance_device_integration.device_adapters.base import AdapterError, DeviceUser, RawPunch
from attendance_device_integration.device_adapters.csv_adapter import CSVAdapter
from attendance_device_integration.device_adapters.http_api import GenericHTTPAdapter
from attendance_device_integration.device_adapters.registry import create_adapter, get_adapter_class
from attendance_device_integration.device_adapters.tcp_ip import GenericTCPAdapter
from attendance_device_integration.device_adapters.zk_protocol import ZKProtocolAdapter


class TestRegistry(unittest.TestCase):
	def test_all_protocol_types_resolve(self):
		for protocol in ("Generic TCP/IP", "ESSL TCP/IP", "ZKTeco Compatible TCP/IP",
						  "Generic HTTP API", "ADMS", "CSV Import", "Excel Import", "Manual Entry"):
			self.assertIsNotNone(get_adapter_class(protocol))

	def test_unknown_protocol_raises(self):
		with self.assertRaises(AdapterError):
			get_adapter_class("Carrier Pigeon Protocol")


class TestCapabilityReporting(unittest.TestCase):
	def test_zk_adapter_reports_full_capabilities(self):
		caps = ZKProtocolAdapter.capabilities()
		for op in ("get_users", "get_attendance_logs", "clear_attendance_logs", "set_device_time", "restart_device"):
			self.assertEqual(caps[op], "SUPPORTED", op)

	def test_generic_tcp_reports_no_attendance_capability(self):
		caps = GenericTCPAdapter.capabilities()
		self.assertEqual(caps["get_attendance_logs"], "NOT_SUPPORTED")
		self.assertEqual(caps["get_users"], "NOT_SUPPORTED")

	def test_incremental_fallback_reported_distinctly(self):
		caps = GenericHTTPAdapter.capabilities()
		# HTTP adapter doesn't override since_last_sync but does support bulk fetch
		self.assertEqual(caps["get_attendance_logs_since_last_sync"], "SUPPORTED (via fallback)")


class TestGenericTCPAdapter(unittest.TestCase):
	def test_missing_ip_raises_clear_error(self):
		adapter = GenericTCPAdapter({"port": 4370})
		with self.assertRaises(AdapterError) as ctx:
			adapter.connect()
		self.assertEqual(ctx.exception.error_code, "INVALID_IP")

	def test_attendance_logs_not_faked(self):
		adapter = GenericTCPAdapter({"ip_address": "10.0.0.1", "port": 4370})
		with self.assertRaises(Exception):
			adapter.get_attendance_logs()

	@patch("attendance_device_integration.device_adapters.tcp_ip.socket.create_connection")
	def test_connection_refused(self, mock_conn):
		mock_conn.side_effect = ConnectionRefusedError()
		adapter = GenericTCPAdapter({"ip_address": "10.0.0.1", "port": 4370})
		with self.assertRaises(AdapterError) as ctx:
			adapter.connect()
		self.assertEqual(ctx.exception.error_code, "CONNECTION_REFUSED")

	@patch("attendance_device_integration.device_adapters.tcp_ip.socket.create_connection")
	def test_successful_connect(self, mock_conn):
		mock_conn.return_value = MagicMock()
		adapter = GenericTCPAdapter({"ip_address": "10.0.0.1", "port": 4370})
		adapter.connect()
		self.assertTrue(adapter.is_connected())


class _FakeUser:
	def __init__(self, user_id, name, card=0, privilege=0):
		self.user_id = user_id
		self.name = name
		self.card = card
		self.privilege = privilege


class _FakeAttendance:
	def __init__(self, user_id, timestamp, punch=0, status=1):
		self.user_id = user_id
		self.timestamp = timestamp
		self.punch = punch
		self.status = status


class TestZKProtocolAdapter(unittest.TestCase):
	@patch("attendance_device_integration.device_adapters.zk_protocol.ZK")
	def test_sdk_missing_reports_clearly(self, mock_zk_class):
		with patch("attendance_device_integration.device_adapters.zk_protocol.ZK", None):
			adapter = ZKProtocolAdapter({"ip_address": "10.0.0.5", "port": 4370})
			with self.assertRaises(AdapterError) as ctx:
				adapter.connect()
			self.assertEqual(ctx.exception.error_code, "SDK_MISSING")

	@patch("attendance_device_integration.device_adapters.zk_protocol.ZK")
	def test_connect_and_get_users(self, mock_zk_class):
		mock_conn = MagicMock()
		mock_conn.get_users.return_value = [_FakeUser("101", "Alice"), _FakeUser("102", "Bob")]
		mock_zk_instance = MagicMock()
		mock_zk_instance.connect.return_value = mock_conn
		mock_zk_class.return_value = mock_zk_instance

		adapter = ZKProtocolAdapter({"ip_address": "10.0.0.5", "port": 4370, "connection_timeout": 10})
		adapter.connect()
		users = adapter.get_users()

		self.assertEqual(len(users), 2)
		self.assertEqual(users[0].device_user_id, "101")
		self.assertEqual(users[0].name, "Alice")

	@patch("attendance_device_integration.device_adapters.zk_protocol.ZK")
	def test_get_attendance_logs_normalizes_direction(self, mock_zk_class):
		mock_conn = MagicMock()
		mock_conn.get_attendance.return_value = [
			_FakeAttendance("101", datetime(2026, 1, 1, 9, 0, 0), punch=0),
			_FakeAttendance("101", datetime(2026, 1, 1, 18, 0, 0), punch=1),
		]
		mock_zk_instance = MagicMock()
		mock_zk_instance.connect.return_value = mock_conn
		mock_zk_class.return_value = mock_zk_instance

		adapter = ZKProtocolAdapter({"ip_address": "10.0.0.5", "port": 4370})
		adapter.connect()
		punches = adapter.get_attendance_logs()

		self.assertEqual(len(punches), 2)
		self.assertEqual(punches[0].direction, "IN")
		self.assertEqual(punches[1].direction, "OUT")

	@patch("attendance_device_integration.device_adapters.zk_protocol.ZK")
	def test_get_attendance_logs_by_date_accepts_string_dates(self, mock_zk_class):
		"""Regression test: the "Sync Today"/"Sync Yesterday" buttons send
		start_date/end_date as plain strings (e.g. "2026-10-05 00:00:00"),
		not datetime objects - this used to crash with
		"combine() argument 1 must be datetime.date, not str"."""
		mock_conn = MagicMock()
		mock_conn.get_attendance.return_value = [
			_FakeAttendance("2", datetime(2026, 10, 5, 9, 0, 0), punch=0),
			_FakeAttendance("2", datetime(2026, 10, 6, 9, 0, 0), punch=0),  # outside range
		]
		mock_zk_instance = MagicMock()
		mock_zk_instance.connect.return_value = mock_conn
		mock_zk_class.return_value = mock_zk_instance

		adapter = ZKProtocolAdapter({"ip_address": "10.0.0.5", "port": 4370})
		adapter.connect()
		punches = adapter.get_attendance_logs_by_date("2026-10-05 00:00:00", "2026-10-05 23:59:59")

		self.assertEqual(len(punches), 1)
		self.assertEqual(punches[0].punch_datetime, datetime(2026, 10, 5, 9, 0, 0))

	@patch("attendance_device_integration.device_adapters.zk_protocol.ZK")
	def test_get_attendance_logs_by_date_accepts_date_only_strings(self, mock_zk_class):
		mock_conn = MagicMock()
		mock_conn.get_attendance.return_value = [_FakeAttendance("2", datetime(2026, 10, 5, 9, 0, 0), punch=0)]
		mock_zk_instance = MagicMock()
		mock_zk_instance.connect.return_value = mock_conn
		mock_zk_class.return_value = mock_zk_instance

		adapter = ZKProtocolAdapter({"ip_address": "10.0.0.5", "port": 4370})
		adapter.connect()
		punches = adapter.get_attendance_logs_by_date("2026-10-05", "2026-10-05")

		self.assertEqual(len(punches), 1)

	@patch("attendance_device_integration.device_adapters.zk_protocol.ZK")
	def test_connection_timeout_raises_clear_error(self, mock_zk_class):
		from zk.exception import ZKNetworkError
		mock_zk_instance = MagicMock()
		mock_zk_instance.connect.side_effect = ZKNetworkError("timed out")
		mock_zk_class.return_value = mock_zk_instance

		adapter = ZKProtocolAdapter({"ip_address": "10.0.0.5", "port": 4370})
		with self.assertRaises(AdapterError) as ctx:
			adapter.connect()
		self.assertEqual(ctx.exception.error_code, "CONNECTION_TIMEOUT")


class TestGenericHTTPAdapter(unittest.TestCase):
	@patch("attendance_device_integration.device_adapters.http_api.requests.request")
	def test_custom_json_mapping(self, mock_request):
		mock_request.return_value = MagicMock(status_code=200, json=lambda: {
			"data": [{"uid": "55", "ts": "2026-01-01 09:00:00", "st": "Check In", "dir": "in", "txn": "T1"}]
		})
		device = {
			"base_url": "http://device.local", "http_api_endpoint": "/logs", "http_method": "GET",
			"authentication_type": "None", "ssl_verification": 1, "connection_timeout": 10,
			"http_response_mapping": (
				'{"device_user_id": "uid", "punch_datetime": "ts", "punch_type": "st", '
				'"direction": "dir", "transaction_id": "txn"}'
			),
		}
		adapter = GenericHTTPAdapter(device)
		adapter.connect()
		punches = adapter.get_attendance_logs()

		self.assertEqual(len(punches), 1)
		self.assertEqual(punches[0].device_user_id, "55")
		self.assertEqual(punches[0].direction, "IN")
		self.assertEqual(punches[0].transaction_id, "T1")

	@patch("attendance_device_integration.device_adapters.http_api.requests.request")
	def test_auth_failure(self, mock_request):
		mock_request.return_value = MagicMock(status_code=401, text="Unauthorized")
		device = {"base_url": "http://device.local", "http_api_endpoint": "/logs",
				  "http_response_mapping": '{"device_user_id": "uid", "punch_datetime": "ts"}'}
		adapter = GenericHTTPAdapter(device)
		adapter.connect()
		with self.assertRaises(AdapterError) as ctx:
			adapter.get_attendance_logs()
		self.assertEqual(ctx.exception.error_code, "AUTHENTICATION_FAILED")

	def test_missing_mapping_raises_clear_error(self):
		device = {"base_url": "http://device.local", "http_api_endpoint": "/logs"}
		adapter = GenericHTTPAdapter(device)
		adapter.connect()
		with patch("attendance_device_integration.device_adapters.http_api.requests.request") as mock_request:
			mock_request.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
			with self.assertRaises(AdapterError) as ctx:
				adapter.get_attendance_logs()
			self.assertEqual(ctx.exception.error_code, "INVALID_CONFIG")


class TestCSVAdapter(unittest.TestCase):
	def _write_csv(self, rows, headers):
		fd, path = tempfile.mkstemp(suffix=".csv")
		with os.fdopen(fd, "w", newline="") as f:
			writer = csv.DictWriter(f, fieldnames=headers)
			writer.writeheader()
			writer.writerows(rows)
		return path

	def test_column_mapping_not_hardcoded(self):
		path = self._write_csv(
			[{"EmpID": "77", "Date": "2026-01-02", "Time": "09:15:00", "Status": "IN"}],
			["EmpID", "Date", "Time", "Status"],
		)
		try:
			device = {
				"import_file": path,
				"import_employee_id_column": "EmpID",
				"import_date_column": "Date", "import_time_column": "Time",
				"import_date_format": "%Y-%m-%d", "import_time_format": "%H:%M:%S",
				"import_punch_type_column": "Status", "import_direction_column": "Status",
			}
			adapter = CSVAdapter(device)
			# Bypass file_manager resolution for this plain-filesystem test file.
			with patch("attendance_device_integration.device_adapters.csv_adapter.frappe.utils.file_manager.get_file_path", return_value=path):
				adapter.connect()
				punches = adapter.get_attendance_logs()

			self.assertEqual(len(punches), 1)
			self.assertEqual(punches[0].device_user_id, "77")
			self.assertEqual(punches[0].punch_datetime, datetime(2026, 1, 2, 9, 15, 0))
		finally:
			os.remove(path)

	def test_missing_employee_column_config_raises(self):
		path = self._write_csv([{"A": "1"}], ["A"])
		try:
			device = {"import_file": path}
			adapter = CSVAdapter(device)
			with patch("attendance_device_integration.device_adapters.csv_adapter.frappe.utils.file_manager.get_file_path", return_value=path):
				adapter.connect()
				with self.assertRaises(AdapterError) as ctx:
					adapter.get_attendance_logs()
				self.assertEqual(ctx.exception.error_code, "INVALID_CONFIG")
		finally:
			os.remove(path)
