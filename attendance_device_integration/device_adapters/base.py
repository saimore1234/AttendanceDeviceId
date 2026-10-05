"""Universal Attendance Device Adapter interface.

Every adapter (ESSL, ZKTeco-compatible, generic TCP/IP, generic HTTP API,
ADMS, CSV, Excel, Manual) implements this contract and takes ALL of its
configuration from an Attendance Device document - never hardcoded.

Not every device supports every operation. Capability reporting is
automatic: a method counts as SUPPORTED if a subclass overrides the base
class's stub, NOT_SUPPORTED if it doesn't. Adapters never need to
maintain a separate capability list by hand - it can't drift out of sync
with the actual implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class AdapterError(Exception):
	"""Raised for any connection/protocol/operation failure. Carries an
	`error_code` so calling code can show a specific, actionable message
	instead of a generic traceback."""

	def __init__(self, message, error_code="ERROR"):
		super().__init__(message)
		self.error_code = error_code


class NotSupportedError(AdapterError):
	def __init__(self, operation, adapter_name):
		super().__init__(
			f"{operation} is not supported by the {adapter_name} adapter",
			error_code="NOT_SUPPORTED",
		)


@dataclass
class DeviceInfo:
	device_id: Optional[str] = None
	firmware_version: Optional[str] = None
	serial_number: Optional[str] = None
	user_count: Optional[int] = None
	log_count: Optional[int] = None
	device_time: Optional[datetime] = None
	extra: dict = field(default_factory=dict)


@dataclass
class DeviceUser:
	device_user_id: str
	name: Optional[str] = None
	card_number: Optional[str] = None
	fingerprint_count: Optional[int] = None
	face_enrolled: Optional[bool] = None
	status: Optional[str] = None


@dataclass
class RawPunch:
	"""One attendance punch exactly as the device reported it - this is
	what every adapter's get_attendance_logs*() methods must return.
	Normalization into Attendance Raw Log happens in services/sync_service.py,
	not here."""

	device_user_id: str
	punch_datetime: datetime
	punch_type: Optional[str] = None       # raw string the device sent
	direction: Optional[str] = None        # IN / OUT / UNKNOWN, if the device says
	verification_type: Optional[str] = None
	work_code: Optional[str] = None
	transaction_id: Optional[str] = None
	device_transaction_id: Optional[str] = None
	raw: Optional[str] = None              # original raw record, for audit


# Pure capability-detection methods: SUPPORTED iff the subclass overrides
# the base stub. get_attendance_logs_since_last_sync is handled separately
# below since the base class gives it a working (non-incremental) fallback
# rather than raising NotSupportedError.
_CAPABILITY_METHODS = (
	"get_device_info", "get_users", "create_user", "update_user", "delete_user",
	"get_attendance_logs", "get_attendance_logs_by_date",
	"clear_attendance_logs", "set_device_time", "get_device_time", "restart_device",
)


class AttendanceDeviceAdapter:
	"""Base class. `device` is an Attendance Device document (or dict-like)."""

	adapter_name = "Base Adapter"

	def __init__(self, device, credential=None):
		self.device = device
		self.credential = credential or {}
		self._connected = False

	# ------------------------------------------------------------
	# Capability reporting
	# ------------------------------------------------------------

	@classmethod
	def capabilities(cls) -> dict:
		"""{"get_users": "SUPPORTED", "create_user": "NOT_SUPPORTED", ...}
		A method is SUPPORTED if the subclass overrides the base stub."""
		result = {}
		for name in _CAPABILITY_METHODS:
			base_fn = getattr(AttendanceDeviceAdapter, name)
			cls_fn = getattr(cls, name)
			result[name] = "SUPPORTED" if cls_fn is not base_fn else "NOT_SUPPORTED"

		# Incremental fetch: natively SUPPORTED if overridden, otherwise it
		# still works via the base class's fallback (fetch-all +
		# duplicate-hash filtering in the sync engine) as long as a bulk
		# fetch method exists at all.
		since_overridden = cls.get_attendance_logs_since_last_sync is not AttendanceDeviceAdapter.get_attendance_logs_since_last_sync
		if since_overridden:
			result["get_attendance_logs_since_last_sync"] = "SUPPORTED"
		elif result["get_attendance_logs"] == "SUPPORTED" or result["get_attendance_logs_by_date"] == "SUPPORTED":
			result["get_attendance_logs_since_last_sync"] = "SUPPORTED (via fallback)"
		else:
			result["get_attendance_logs_since_last_sync"] = "NOT_SUPPORTED"

		return result

	def is_supported(self, operation: str) -> bool:
		return self.capabilities().get(operation) == "SUPPORTED"

	# ------------------------------------------------------------
	# Lifecycle - every adapter must implement these two + test_connection
	# ------------------------------------------------------------

	def connect(self) -> None:
		raise NotImplementedError

	def disconnect(self) -> None:
		raise NotImplementedError

	def is_connected(self) -> bool:
		return self._connected

	def test_connection(self) -> dict:
		"""Connect, fetch basic info, disconnect. Never raises - every
		failure is reported in the returned dict so the UI can show it
		cleanly instead of a stack trace."""
		import time

		started = time.monotonic()
		was_connected = self.is_connected()
		try:
			if not was_connected:
				self.connect()
			info = None
			if self.is_supported("get_device_info"):
				try:
					info = self.get_device_info()
				except AdapterError:
					pass
			return {
				"success": True,
				"adapter": self.adapter_name,
				"capabilities": self.capabilities(),
				"device_info": info.__dict__ if info else None,
				"elapsed_seconds": round(time.monotonic() - started, 3),
			}
		except AdapterError as e:
			return {
				"success": False,
				"adapter": self.adapter_name,
				"error": str(e),
				"error_code": e.error_code,
				"elapsed_seconds": round(time.monotonic() - started, 3),
			}
		finally:
			if not was_connected:
				try:
					self.disconnect()
				except Exception:
					pass

	# ------------------------------------------------------------
	# Capability methods - base stubs all raise NotSupportedError.
	# Adapters override whichever of these their protocol can do.
	# ------------------------------------------------------------

	def get_device_info(self) -> DeviceInfo:
		raise NotSupportedError("get_device_info", self.adapter_name)

	def get_users(self) -> list[DeviceUser]:
		raise NotSupportedError("get_users", self.adapter_name)

	def create_user(self, device_user_id: str, **kwargs) -> None:
		raise NotSupportedError("create_user", self.adapter_name)

	def update_user(self, device_user_id: str, **kwargs) -> None:
		raise NotSupportedError("update_user", self.adapter_name)

	def delete_user(self, device_user_id: str) -> None:
		raise NotSupportedError("delete_user", self.adapter_name)

	def get_attendance_logs(self) -> list[RawPunch]:
		raise NotSupportedError("get_attendance_logs", self.adapter_name)

	def get_attendance_logs_by_date(self, start_date, end_date) -> list[RawPunch]:
		raise NotSupportedError("get_attendance_logs_by_date", self.adapter_name)

	def get_attendance_logs_since_last_sync(self, since: Optional[datetime]) -> list[RawPunch]:
		"""Default fallback: adapters that can't filter server-side just
		fetch everything and let the sync engine's duplicate-hash check
		discard what's already been processed. Adapters that CAN filter
		server-side should override this for real incremental fetching."""
		return self.get_attendance_logs()

	def clear_attendance_logs(self) -> None:
		raise NotSupportedError("clear_attendance_logs", self.adapter_name)

	def set_device_time(self, dt: datetime) -> None:
		raise NotSupportedError("set_device_time", self.adapter_name)

	def get_device_time(self) -> datetime:
		raise NotSupportedError("get_device_time", self.adapter_name)

	def restart_device(self) -> None:
		raise NotSupportedError("restart_device", self.adapter_name)

	def __enter__(self):
		self.connect()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		try:
			self.disconnect()
		except Exception:
			pass
