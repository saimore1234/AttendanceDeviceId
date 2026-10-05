"""Manual Entry adapter - no physical device at all. Used when
Protocol Type = "Manual Entry": attendance is recorded by a human (e.g.
via a manual Employee Checkin form) rather than fetched from anything.
Exists so the adapter registry/capability-reporting machinery has a
uniform entry even for "no device" devices."""

from __future__ import annotations

from attendance_device_integration.device_adapters.base import AttendanceDeviceAdapter, DeviceInfo


class ManualAdapter(AttendanceDeviceAdapter):
	adapter_name = "Manual Entry"

	def connect(self) -> None:
		self._connected = True

	def disconnect(self) -> None:
		self._connected = False

	def get_device_info(self) -> DeviceInfo:
		return DeviceInfo(device_id=self.device.get("device_id"), extra={"note": "No physical device - manual entry only."})

	def get_attendance_logs(self):
		return []
