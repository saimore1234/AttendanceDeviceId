"""Implements the exact same AttendanceDeviceAdapter interface as every
other adapter, but delegates each call to a remote Local Agent over HTTP
instead of talking to the device directly - used when an Attendance
Device's Connection Mode is "Local Agent" (ERPNext is remote from the
device's network).

Because this presents the same interface, nothing elsewhere in the app
(sync_service, api/devices) needs to know or care whether a given device
is being driven directly or through an agent - see
device_adapters/registry.get_adapter_for_device().
"""

from __future__ import annotations

from datetime import datetime

from attendance_device_integration.device_adapters.base import (
	AdapterError, AttendanceDeviceAdapter, DeviceInfo, DeviceUser, RawPunch,
)
from attendance_device_integration.services import local_agent_client


def _device_dict(device) -> dict:
	skip = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
	raw = device.as_dict() if hasattr(device, "as_dict") else dict(device)
	return {k: v for k, v in raw.items() if k not in skip and not str(k).startswith("_")}


class RemoteAgentAdapter(AttendanceDeviceAdapter):
	adapter_name = "Local Agent (remote)"

	def connect(self) -> None:
		agent_url = self.device.get("local_agent_url")
		if not agent_url:
			raise AdapterError("No Local Agent URL configured on this device", error_code="INVALID_CONFIG")
		self._connected = True  # the actual device connection happens per-call on the agent side

	def disconnect(self) -> None:
		self._connected = False

	def _args(self):
		return self.device.get("local_agent_url"), self.credential.get("bearer_token"), _device_dict(self.device)

	def test_connection(self) -> dict:
		import time
		started = time.monotonic()
		try:
			result = local_agent_client.test_connection(*self._args())
			return {
				"success": True, "adapter": "ESSL/ZKTeco via Local Agent",
				"capabilities": self.capabilities(),
				"device_info": result.get("device_info"),
				"elapsed_seconds": round(time.monotonic() - started, 3),
			}
		except AdapterError as e:
			return {"success": False, "adapter": "Local Agent", "error": str(e), "error_code": e.error_code,
					"elapsed_seconds": round(time.monotonic() - started, 3)}

	def get_device_info(self) -> DeviceInfo:
		result = local_agent_client.get_device_info(*self._args())
		return DeviceInfo(
			device_id=self.device.get("device_id"),
			firmware_version=result.get("firmware_version"),
			serial_number=result.get("serial_number"),
			user_count=result.get("user_count"),
			extra={"platform": result.get("platform"), "mac": result.get("mac")},
		)

	def get_users(self) -> list[DeviceUser]:
		result = local_agent_client.get_users(*self._args())
		return [DeviceUser(**u) for u in result.get("users", [])]

	def get_attendance_logs(self):
		result = local_agent_client.get_attendance_logs(*self._args())
		return self._to_punches(result.get("punches", []))

	def get_attendance_logs_by_date(self, start_date, end_date):
		agent_url, token, device_dict = self._args()
		result = local_agent_client.get_attendance_logs(agent_url, token, device_dict, start_date=start_date, end_date=end_date)
		return self._to_punches(result.get("punches", []))

	def get_attendance_logs_since_last_sync(self, since):
		agent_url, token, device_dict = self._args()
		result = local_agent_client.get_attendance_logs(agent_url, token, device_dict, since=since)
		return self._to_punches(result.get("punches", []))

	@staticmethod
	def _to_punches(raw_punches):
		return [
			RawPunch(
				device_user_id=p["device_user_id"],
				punch_datetime=datetime.fromisoformat(p["punch_datetime"]),
				punch_type=p.get("punch_type"),
				direction=p.get("direction", "UNKNOWN"),
				transaction_id=p.get("transaction_id"),
				raw=str(p),
			)
			for p in raw_punches
		]

	def clear_attendance_logs(self) -> None:
		local_agent_client.clear_logs(*self._args())

	def get_device_time(self) -> datetime:
		result = local_agent_client.get_time(*self._args())
		return datetime.fromisoformat(result["device_time"])

	def set_device_time(self, dt: datetime) -> None:
		local_agent_client.set_time(*self._args())

	def restart_device(self) -> None:
		local_agent_client.restart(*self._args())

	@classmethod
	def capabilities(cls) -> dict:
		# Mirrors ZKProtocolAdapter's capabilities, since that's what the
		# agent actually runs - this class itself overrides every method,
		# which would otherwise make the generic base-class detection
		# report everything as SUPPORTED regardless of the agent's own
		# limitations. Kept explicit and honest instead.
		return {
			"get_device_info": "SUPPORTED", "get_users": "SUPPORTED",
			"create_user": "NOT_SUPPORTED", "update_user": "NOT_SUPPORTED", "delete_user": "NOT_SUPPORTED",
			"get_attendance_logs": "SUPPORTED", "get_attendance_logs_by_date": "SUPPORTED",
			"get_attendance_logs_since_last_sync": "SUPPORTED",
			"clear_attendance_logs": "SUPPORTED", "set_device_time": "SUPPORTED",
			"get_device_time": "SUPPORTED", "restart_device": "SUPPORTED",
		}
