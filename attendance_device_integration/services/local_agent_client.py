"""Thin HTTP client the ERPNext server uses to talk to a Local Agent
running on the device's own network, when an Attendance Device's
Connection Mode is "Local Agent" rather than "Server" - i.e. ERPNext
itself can't reach the device directly (different network/location).
"""

from __future__ import annotations

import requests

from attendance_device_integration.device_adapters.base import AdapterError


def _headers(token):
	return {"Authorization": f"Bearer {token}"} if token else {}


def _call(agent_url, path, token, device_dict, timeout=15, **extra):
	if not agent_url:
		raise AdapterError("No Local Agent URL configured on this device", error_code="INVALID_CONFIG")

	try:
		response = requests.post(
			f"{agent_url.rstrip('/')}{path}",
			headers=_headers(token),
			json={"device": device_dict, **extra},
			timeout=timeout,
		)
	except requests.exceptions.Timeout:
		raise AdapterError("Local Agent did not respond in time", error_code="CONNECTION_TIMEOUT")
	except requests.exceptions.ConnectionError:
		raise AdapterError("Could not reach the Local Agent - is it running and is the URL/tunnel correct?",
							error_code="CONNECTION_FAILED")
	except requests.exceptions.RequestException as e:
		raise AdapterError(f"Local Agent request failed: {e}", error_code="API_ERROR")

	if response.status_code == 401:
		raise AdapterError("Local Agent rejected the configured token", error_code="AUTHENTICATION_FAILED")
	if response.status_code >= 400:
		raise AdapterError(f"Local Agent returned {response.status_code}: {response.text[:200]}", error_code="API_ERROR")

	try:
		data = response.json()
	except ValueError:
		raise AdapterError("Local Agent returned a non-JSON response", error_code="API_ERROR")

	if not data.get("success"):
		raise AdapterError(data.get("error") or "Local Agent reported failure",
							error_code=data.get("error_code") or "ERROR")
	return data


def test_connection(agent_url, token, device_dict):
	return _call(agent_url, "/test-connection", token, device_dict)


def get_device_info(agent_url, token, device_dict):
	return _call(agent_url, "/device-info", token, device_dict)


def get_users(agent_url, token, device_dict):
	return _call(agent_url, "/users", token, device_dict)


def get_attendance_logs(agent_url, token, device_dict, since=None, start_date=None, end_date=None):
	extra = {}
	if since:
		extra["since"] = since.isoformat() if hasattr(since, "isoformat") else since
	if start_date:
		extra["start_date"] = start_date.isoformat() if hasattr(start_date, "isoformat") else start_date
	if end_date:
		extra["end_date"] = end_date.isoformat() if hasattr(end_date, "isoformat") else end_date
	return _call(agent_url, "/attendance-logs", token, device_dict, **extra)


def clear_logs(agent_url, token, device_dict):
	return _call(agent_url, "/clear-logs", token, device_dict)


def get_time(agent_url, token, device_dict):
	return _call(agent_url, "/get-time", token, device_dict)


def set_time(agent_url, token, device_dict):
	return _call(agent_url, "/set-time", token, device_dict)


def restart(agent_url, token, device_dict):
	return _call(agent_url, "/restart", token, device_dict)
