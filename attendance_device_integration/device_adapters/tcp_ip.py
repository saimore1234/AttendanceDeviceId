"""Generic TCP/IP adapter.

Verifies the device is reachable at the network level (a real, working
socket connect/test), but does NOT invent an attendance protocol. Pulling
actual punches requires a protocol-specific adapter (ESSL/ZKTeco/etc) -
this one is for devices whose exact protocol isn't known yet, or for
confirming basic network reachability before picking a real adapter.
"""

from __future__ import annotations

import socket
from datetime import datetime

from attendance_device_integration.device_adapters.base import AdapterError, AttendanceDeviceAdapter, DeviceInfo


class GenericTCPAdapter(AttendanceDeviceAdapter):
	adapter_name = "Generic TCP/IP"

	def __init__(self, device, credential=None):
		super().__init__(device, credential)
		self._sock = None

	def connect(self) -> None:
		ip = self.device.get("ip_address")
		if not ip:
			raise AdapterError("No IP Address configured on this device", error_code="INVALID_IP")
		port = self.device.get("port")
		if not port:
			raise AdapterError("No Port configured on this device", error_code="INVALID_PORT")
		timeout = float(self.device.get("connection_timeout") or 10)

		try:
			self._sock = socket.create_connection((ip, int(port)), timeout=timeout)
			self._connected = True
		except socket.timeout:
			raise AdapterError(f"Connection to {ip}:{port} timed out", error_code="CONNECTION_TIMEOUT")
		except ConnectionRefusedError:
			raise AdapterError(f"Connection to {ip}:{port} was refused", error_code="CONNECTION_REFUSED")
		except OSError as e:
			raise AdapterError(f"Could not connect to {ip}:{port}: {e}", error_code="CONNECTION_FAILED")

	def disconnect(self) -> None:
		if self._sock is not None:
			try:
				self._sock.close()
			except Exception:
				pass
		self._sock = None
		self._connected = False

	def get_device_info(self) -> DeviceInfo:
		# Network-level reachability only - no protocol to ask for real info.
		return DeviceInfo(
			device_id=self.device.get("device_id"),
			extra={"note": "Device connected at network level, but attendance protocol is not configured. "
						   "Select ESSL TCP/IP or ZKTeco Compatible TCP/IP if this device speaks that protocol."},
		)
