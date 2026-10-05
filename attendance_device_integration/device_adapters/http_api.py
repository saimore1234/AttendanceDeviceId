"""Generic HTTP/REST API adapter.

The administrator configures the base URL, endpoint, method, auth, and a
JSON field-mapping (http_response_mapping) that tells this adapter how to
read device_user_id/punch_datetime/punch_type/transaction_id/direction
out of whatever shape the API actually returns. No API shape is assumed.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import requests

from attendance_device_integration.device_adapters.base import AdapterError, AttendanceDeviceAdapter, DeviceInfo, RawPunch

_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _resolve_path(data, path):
	if not path:
		return None
	current = data
	for name, index in _TOKEN_RE.findall(path):
		try:
			current = current[name] if name else current[int(index)]
		except (KeyError, IndexError, TypeError):
			return None
	return current


def _parse_datetime(value):
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return datetime.fromtimestamp(value)
	for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%d-%m-%Y %H:%M:%S"):
		try:
			return datetime.strptime(str(value), fmt)
		except ValueError:
			continue
	raise AdapterError(f"Could not parse punch datetime: {value!r}", error_code="INVALID_DATETIME")


class GenericHTTPAdapter(AttendanceDeviceAdapter):
	adapter_name = "Generic HTTP API"

	def connect(self) -> None:
		if not self.device.get("base_url"):
			raise AdapterError("No Base URL configured on this device", error_code="INVALID_URL")
		self._connected = True  # HTTP is stateless; connect() just validates config

	def disconnect(self) -> None:
		self._connected = False

	def _headers(self):
		headers = {}
		raw = self.device.get("http_headers")
		if raw:
			try:
				headers.update(json.loads(raw))
			except json.JSONDecodeError:
				raise AdapterError("Extra Headers is not valid JSON", error_code="INVALID_CONFIG")

		auth_type = self.device.get("authentication_type") or "None"
		if auth_type == "Bearer Token" and self.credential.get("bearer_token"):
			headers["Authorization"] = f"Bearer {self.credential['bearer_token']}"
		elif auth_type == "API Key" and self.credential.get("api_key"):
			headers["X-API-Key"] = self.credential["api_key"]
		return headers

	def _auth(self):
		if (self.device.get("authentication_type") or "None") == "Basic":
			return (self.credential.get("username") or "", self.credential.get("password") or "")
		return None

	def _request(self, endpoint, params=None):
		url = (self.device.get("base_url") or "").rstrip("/") + "/" + (endpoint or "").lstrip("/")
		timeout = float(self.device.get("connection_timeout") or 10)
		verify_ssl = bool(self.device.get("ssl_verification", True))

		try:
			response = requests.request(
				method=(self.device.get("http_method") or "GET").upper(),
				url=url, headers=self._headers(), auth=self._auth(),
				params=params, timeout=timeout, verify=verify_ssl,
			)
		except requests.exceptions.Timeout:
			raise AdapterError(f"Request to {url} timed out", error_code="CONNECTION_TIMEOUT")
		except requests.exceptions.ConnectionError as e:
			raise AdapterError(f"Could not reach {url}: {e}", error_code="CONNECTION_FAILED")
		except requests.exceptions.RequestException as e:
			raise AdapterError(f"Request failed: {e}", error_code="API_ERROR")

		if response.status_code in (401, 403):
			raise AdapterError(f"Authentication failed ({response.status_code})", error_code="AUTHENTICATION_FAILED")
		if response.status_code >= 400:
			raise AdapterError(f"API returned {response.status_code}: {response.text[:200]}", error_code="API_ERROR")

		try:
			return response.json()
		except ValueError:
			raise AdapterError("API did not return valid JSON", error_code="API_ERROR")

	def get_device_info(self) -> DeviceInfo:
		return DeviceInfo(device_id=self.device.get("device_id"), extra={"base_url": self.device.get("base_url")})

	def get_attendance_logs(self):
		return self.get_attendance_logs_by_date(None, None)

	def get_attendance_logs_by_date(self, start_date, end_date):
		params = {}
		if start_date:
			params["start_date"] = str(start_date)
		if end_date:
			params["end_date"] = str(end_date)

		data = self._request(self.device.get("http_api_endpoint"), params=params)

		mapping_raw = self.device.get("http_response_mapping")
		if not mapping_raw:
			raise AdapterError(
				"No Response Field Mapping configured - cannot tell which JSON fields are "
				"device_user_id/punch_datetime/etc.", error_code="INVALID_CONFIG",
			)
		try:
			mapping = json.loads(mapping_raw)
		except json.JSONDecodeError:
			raise AdapterError("Response Field Mapping is not valid JSON", error_code="INVALID_CONFIG")

		records = data if isinstance(data, list) else data.get("data") or data.get("records") or [data]

		punches = []
		for record in records:
			device_user_id = _resolve_path(record, mapping.get("device_user_id"))
			punch_dt_raw = _resolve_path(record, mapping.get("punch_datetime"))
			if device_user_id is None or punch_dt_raw is None:
				continue
			punches.append(RawPunch(
				device_user_id=str(device_user_id),
				punch_datetime=_parse_datetime(punch_dt_raw),
				punch_type=str(_resolve_path(record, mapping.get("punch_type")) or ""),
				direction=str(_resolve_path(record, mapping.get("direction")) or "UNKNOWN").upper(),
				transaction_id=str(_resolve_path(record, mapping.get("transaction_id")) or "") or None,
				raw=json.dumps(record),
			))
		return punches
