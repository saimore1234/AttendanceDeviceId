"""ADMS adapter.

ADMS devices typically PUSH attendance data to a server URL (the classic
ZKTeco ADMS "/iclock/cdata" style push protocol) rather than waiting to be
pulled. That means for devices in Push mode, there is nothing for this
adapter's get_attendance_logs() to fetch - the data arrives independently
via the webhook endpoint
(attendance_device_integration.api.webhook.device_webhook) and lands
directly in Attendance Raw Log. This adapter's job in Push mode is just
to report that clearly rather than pretending a pull happened.

For devices configured in Pull mode (some ADMS-compatible panels expose a
pull endpoint), this falls back to the same configurable HTTP mapping as
the Generic HTTP adapter.
"""

from __future__ import annotations

from attendance_device_integration.device_adapters.base import AdapterError, AttendanceDeviceAdapter, DeviceInfo
from attendance_device_integration.device_adapters.http_api import GenericHTTPAdapter


class ADMSAdapter(AttendanceDeviceAdapter):
	adapter_name = "ADMS"

	def __init__(self, device, credential=None):
		super().__init__(device, credential)
		self._http_delegate = None

	def _mode(self):
		return self.device.get("adms_push_pull_mode") or "Push"

	def connect(self) -> None:
		if self._mode() == "Pull":
			self._http_delegate = GenericHTTPAdapter(self.device, self.credential)
			self._http_delegate.device = dict(self.device)
			self._http_delegate.device["http_api_endpoint"] = self.device.get("adms_attendance_endpoint")
			self._http_delegate.connect()
		self._connected = True

	def disconnect(self) -> None:
		if self._http_delegate:
			self._http_delegate.disconnect()
		self._connected = False

	def get_device_info(self) -> DeviceInfo:
		return DeviceInfo(
			device_id=self.device.get("device_id"),
			extra={"mode": self._mode(), "note": (
				"Push mode: this device sends data to the webhook endpoint directly; "
				"nothing to pull. Check Attendance Raw Log filtered by this device."
				if self._mode() == "Push" else
				"Pull mode: fetching via the configured ADMS Attendance Endpoint."
			)},
		)

	def get_attendance_logs(self):
		if self._mode() == "Push":
			raise AdapterError(
				"This device is in ADMS Push mode - it sends data to the webhook endpoint directly, "
				"there is nothing to pull. Check Attendance Raw Log for records received via webhook.",
				error_code="NOT_SUPPORTED",
			)
		return self._http_delegate.get_attendance_logs_by_date(None, None)

	def get_attendance_logs_by_date(self, start_date, end_date):
		if self._mode() == "Push":
			raise AdapterError(
				"This device is in ADMS Push mode - data arrives via webhook, not by pulling a date range.",
				error_code="NOT_SUPPORTED",
			)
		return self._http_delegate.get_attendance_logs_by_date(start_date, end_date)
