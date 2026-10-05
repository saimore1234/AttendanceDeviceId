"""Real, working adapter for devices that speak the ZK communication
protocol over TCP/IP - built on the `pyzk` library (pip install pyzk).

A large share of ESSL and ZKTeco TCP/IP biometric terminals use this
protocol (ESSL's lower-cost TCP/IP range has historically shipped on
ZK-compatible firmware), which is why both "ESSL TCP/IP" and "ZKTeco
Compatible TCP/IP" protocol types share this one implementation rather
than being faked as two separate things. This is NOT a claim that every
ESSL or ZKTeco model is compatible - if a specific model uses a different
protocol, connect()/test_connection() will fail with a clear error rather
than silently pretending to work.
"""

from __future__ import annotations

from datetime import date, datetime

from attendance_device_integration.device_adapters.base import (
	AdapterError, AttendanceDeviceAdapter, DeviceInfo, DeviceUser, RawPunch,
)


def _to_datetime(value, end_of_day: bool) -> datetime:
	"""Accepts a datetime, a date, or a string (the API/whitelisted
	methods receive plain strings from the browser - e.g. the "Sync
	Today"/"Sync Yesterday" buttons send "2026-10-05 00:00:00")."""
	if isinstance(value, datetime):
		return value
	if isinstance(value, str):
		try:
			return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
		except ValueError:
			pass
		try:
			parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
			return datetime.combine(parsed_date, datetime.max.time() if end_of_day else datetime.min.time())
		except ValueError:
			pass
		raise AdapterError(f"Could not parse date/datetime: {value!r}", error_code="INVALID_DATETIME")
	if isinstance(value, date):
		return datetime.combine(value, datetime.max.time() if end_of_day else datetime.min.time())
	raise AdapterError(f"Unsupported date type for {value!r}: {type(value)}", error_code="INVALID_DATETIME")

try:
	from zk import ZK
	from zk.exception import ZKErrorConnection, ZKErrorResponse, ZKNetworkError
except ImportError:
	ZK = None
	ZKErrorConnection = ZKErrorResponse = ZKNetworkError = Exception


class ZKProtocolAdapter(AttendanceDeviceAdapter):
	adapter_name = "ZK Protocol (TCP/IP)"

	def __init__(self, device, credential=None):
		super().__init__(device, credential)
		self._zk = None
		self._conn = None

	def connect(self) -> None:
		if ZK is None:
			raise AdapterError(
				"Required library 'pyzk' is not installed on the server. Install it with: pip install pyzk",
				error_code="SDK_MISSING",
			)

		ip = self.device.get("ip_address")
		if not ip:
			raise AdapterError("No IP Address configured on this device", error_code="INVALID_IP")
		port = int(self.device.get("port") or 4370)
		timeout = int(self.device.get("connection_timeout") or 10)
		password = int(self.credential.get("password") or 0) if str(self.credential.get("password") or "").isdigit() else 0

		self._zk = ZK(ip, port=port, timeout=timeout, password=password, force_udp=False, ommit_ping=False)
		try:
			self._conn = self._zk.connect()
			self._connected = True
		except ZKNetworkError as e:
			raise AdapterError(f"Could not reach {ip}:{port} - {e}", error_code="CONNECTION_TIMEOUT")
		except ZKErrorConnection as e:
			raise AdapterError(f"Connection to {ip}:{port} failed - {e}", error_code="AUTHENTICATION_FAILED")
		except Exception as e:
			raise AdapterError(f"Could not connect to device at {ip}:{port}: {e}", error_code="CONNECTION_FAILED")

	def disconnect(self) -> None:
		if self._conn is not None:
			try:
				self._conn.disconnect()
			except Exception:
				pass
		self._conn = None
		self._connected = False

	def _require_connection(self):
		if not self._connected or self._conn is None:
			raise AdapterError("Not connected to device", error_code="NOT_CONNECTED")

	def get_device_info(self) -> DeviceInfo:
		self._require_connection()
		try:
			return DeviceInfo(
				device_id=self.device.get("device_id"),
				firmware_version=self._safe(self._conn.get_firmware_version),
				serial_number=self._safe(self._conn.get_serialnumber),
				user_count=len(self._safe(self._conn.get_users, default=[]) or []),
				device_time=self._safe(self._conn.get_time),
				extra={"platform": self._safe(self._conn.get_platform), "mac": self._safe(self._conn.get_mac)},
			)
		except (ZKErrorResponse, Exception) as e:
			raise AdapterError(f"Could not read device info: {e}", error_code="PROTOCOL_ERROR")

	def _safe(self, fn, default=None):
		try:
			return fn()
		except Exception:
			return default

	def get_users(self) -> list[DeviceUser]:
		self._require_connection()
		try:
			users = self._conn.get_users()
		except Exception as e:
			raise AdapterError(f"Could not fetch users: {e}", error_code="PROTOCOL_ERROR")

		return [
			DeviceUser(
				device_user_id=str(u.user_id),
				name=u.name,
				card_number=str(u.card) if getattr(u, "card", None) else None,
				status=str(getattr(u, "privilege", "")),
			)
			for u in users
		]

	def create_user(self, device_user_id: str, **kwargs) -> None:
		self._require_connection()
		try:
			self._conn.set_user(
				uid=int(kwargs.get("uid") or device_user_id),
				name=kwargs.get("name", ""),
				privilege=kwargs.get("privilege", 0),
				password=kwargs.get("password", ""),
				user_id=str(device_user_id),
				card=kwargs.get("card", 0),
			)
		except Exception as e:
			raise AdapterError(f"Could not create user {device_user_id}: {e}", error_code="PROTOCOL_ERROR")

	def update_user(self, device_user_id: str, **kwargs) -> None:
		# pyzk's set_user() upserts - same call as create.
		self.create_user(device_user_id, **kwargs)

	def delete_user(self, device_user_id: str) -> None:
		self._require_connection()
		try:
			self._conn.delete_user(user_id=str(device_user_id))
		except Exception as e:
			raise AdapterError(f"Could not delete user {device_user_id}: {e}", error_code="PROTOCOL_ERROR")

	def get_attendance_logs(self) -> list[RawPunch]:
		self._require_connection()
		try:
			records = self._conn.get_attendance()
		except Exception as e:
			raise AdapterError(f"Could not fetch attendance logs: {e}", error_code="PROTOCOL_ERROR")

		punches = []
		for r in records or []:
			# pyzk's AttendanceRecord typically has: user_id, timestamp, status, punch
			direction = "UNKNOWN"
			punch_val = getattr(r, "punch", None)
			if punch_val in (0,):
				direction = "IN"
			elif punch_val in (1,):
				direction = "OUT"

			punches.append(RawPunch(
				device_user_id=str(r.user_id),
				punch_datetime=r.timestamp,
				punch_type=str(getattr(r, "status", "")),
				direction=direction,
				verification_type=None,
				raw=str(r),
			))
		return punches

	def get_attendance_logs_by_date(self, start_date, end_date) -> list[RawPunch]:
		all_logs = self.get_attendance_logs()
		start_dt = _to_datetime(start_date, end_of_day=False)
		end_dt = _to_datetime(end_date, end_of_day=True)
		return [p for p in all_logs if start_dt <= p.punch_datetime <= end_dt]

	def get_attendance_logs_since_last_sync(self, since):
		all_logs = self.get_attendance_logs()
		if since is None:
			return all_logs
		since_dt = _to_datetime(since, end_of_day=False)
		return [p for p in all_logs if p.punch_datetime > since_dt]

	def clear_attendance_logs(self) -> None:
		self._require_connection()
		try:
			self._conn.clear_attendance()
		except Exception as e:
			raise AdapterError(f"Could not clear device logs: {e}", error_code="PROTOCOL_ERROR")

	def get_device_time(self) -> datetime:
		self._require_connection()
		try:
			return self._conn.get_time()
		except Exception as e:
			raise AdapterError(f"Could not read device time: {e}", error_code="PROTOCOL_ERROR")

	def set_device_time(self, dt: datetime) -> None:
		self._require_connection()
		try:
			self._conn.set_time(dt)
		except Exception as e:
			raise AdapterError(f"Could not set device time: {e}", error_code="PROTOCOL_ERROR")

	def restart_device(self) -> None:
		self._require_connection()
		try:
			self._conn.restart()
		except Exception as e:
			raise AdapterError(f"Could not restart device: {e}", error_code="PROTOCOL_ERROR")
