"""Local Agent dispatch + RemoteAgentAdapter - no real agent process
required, the HTTP layer is mocked."""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from attendance_device_integration.device_adapters.base import AdapterError
from attendance_device_integration.device_adapters.registry import get_adapter_for_device
from attendance_device_integration.device_adapters.remote_agent_adapter import RemoteAgentAdapter
from attendance_device_integration.device_adapters.tcp_ip import GenericTCPAdapter
from attendance_device_integration.device_adapters.zk_protocol import ZKProtocolAdapter


class TestDispatch(unittest.TestCase):
	def test_server_mode_gets_direct_adapter(self):
		device = {"protocol_type": "ZKTeco Compatible TCP/IP", "connection_mode": "Server"}
		adapter = get_adapter_for_device(device)
		self.assertIsInstance(adapter, ZKProtocolAdapter)
		self.assertNotIsInstance(adapter, RemoteAgentAdapter)

	def test_default_connection_mode_is_server(self):
		device = {"protocol_type": "Generic TCP/IP"}  # no connection_mode key at all
		adapter = get_adapter_for_device(device)
		self.assertIsInstance(adapter, GenericTCPAdapter)

	def test_local_agent_mode_gets_remote_adapter(self):
		device = {"protocol_type": "ESSL TCP/IP", "connection_mode": "Local Agent", "local_agent_url": "http://agent.local:8585"}
		adapter = get_adapter_for_device(device)
		self.assertIsInstance(adapter, RemoteAgentAdapter)


class TestRemoteAgentAdapter(unittest.TestCase):
	def _device(self):
		return {
			"protocol_type": "ESSL TCP/IP", "connection_mode": "Local Agent",
			"local_agent_url": "http://agent.local:8585", "device_id": "X990-1",
			"ip_address": "192.168.0.56", "port": 4370,
		}

	def test_missing_agent_url_raises_clear_error(self):
		adapter = RemoteAgentAdapter({"connection_mode": "Local Agent"})
		with self.assertRaises(AdapterError) as ctx:
			adapter.connect()
		self.assertEqual(ctx.exception.error_code, "INVALID_CONFIG")

	@patch("attendance_device_integration.services.local_agent_client.requests.post")
	def test_get_device_info_via_agent(self, mock_post):
		mock_post.return_value = MagicMock(status_code=200, json=lambda: {
			"success": True, "firmware_version": "6.60", "serial_number": "ABC123", "user_count": 42,
		})
		adapter = RemoteAgentAdapter(self._device(), credential={"bearer_token": "tok123"})
		adapter.connect()
		info = adapter.get_device_info()

		self.assertEqual(info.firmware_version, "6.60")
		self.assertEqual(info.user_count, 42)
		# Confirm the agent call actually carried the auth header and the device payload.
		_, kwargs = mock_post.call_args
		self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok123")
		self.assertEqual(kwargs["json"]["device"]["ip_address"], "192.168.0.56")

	@patch("attendance_device_integration.services.local_agent_client.requests.post")
	def test_get_attendance_logs_via_agent(self, mock_post):
		mock_post.return_value = MagicMock(status_code=200, json=lambda: {
			"success": True, "punches": [
				{"device_user_id": "77", "punch_datetime": "2026-01-01T09:00:00", "direction": "IN"},
			],
		})
		adapter = RemoteAgentAdapter(self._device(), credential={"bearer_token": "tok123"})
		adapter.connect()
		punches = adapter.get_attendance_logs()

		self.assertEqual(len(punches), 1)
		self.assertEqual(punches[0].device_user_id, "77")
		self.assertEqual(punches[0].punch_datetime, datetime(2026, 1, 1, 9, 0, 0))

	@patch("attendance_device_integration.services.local_agent_client.requests.post")
	def test_agent_unreachable_raises_clear_error(self, mock_post):
		import requests
		mock_post.side_effect = requests.exceptions.ConnectionError()
		adapter = RemoteAgentAdapter(self._device(), credential={"bearer_token": "tok123"})
		adapter.connect()
		with self.assertRaises(AdapterError) as ctx:
			adapter.get_device_info()
		self.assertEqual(ctx.exception.error_code, "CONNECTION_FAILED")

	@patch("attendance_device_integration.services.local_agent_client.requests.post")
	def test_wrong_agent_token_raises_auth_error(self, mock_post):
		mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")
		adapter = RemoteAgentAdapter(self._device(), credential={"bearer_token": "wrong"})
		adapter.connect()
		with self.assertRaises(AdapterError) as ctx:
			adapter.get_device_info()
		self.assertEqual(ctx.exception.error_code, "AUTHENTICATION_FAILED")

	def test_capabilities_are_explicit_not_inherited(self):
		caps = RemoteAgentAdapter.capabilities()
		self.assertEqual(caps["get_attendance_logs"], "SUPPORTED")
		self.assertEqual(caps["create_user"], "NOT_SUPPORTED")
