"""Factory: Protocol Type (a plain string from the Attendance Device
doctype) -> adapter class. The only place that maps a protocol name to
code - adding a future vendor adapter means adding one line here and one
adapter module, nothing else in the app needs to change.
"""

from __future__ import annotations

from attendance_device_integration.device_adapters.adms import ADMSAdapter
from attendance_device_integration.device_adapters.base import AdapterError
from attendance_device_integration.device_adapters.csv_adapter import CSVAdapter
from attendance_device_integration.device_adapters.essl import ESSLAdapter
from attendance_device_integration.device_adapters.excel_adapter import ExcelAdapter
from attendance_device_integration.device_adapters.generic import ManualAdapter
from attendance_device_integration.device_adapters.http_api import GenericHTTPAdapter
from attendance_device_integration.device_adapters.tcp_ip import GenericTCPAdapter
from attendance_device_integration.device_adapters.zkteco import ZKTecoAdapter

DEVICE_ADAPTERS = {
	"Generic TCP/IP": GenericTCPAdapter,
	"ESSL TCP/IP": ESSLAdapter,
	"ZKTeco Compatible TCP/IP": ZKTecoAdapter,
	"Generic HTTP API": GenericHTTPAdapter,
	"ADMS": ADMSAdapter,
	"CSV Import": CSVAdapter,
	"Excel Import": ExcelAdapter,
	"Manual Entry": ManualAdapter,
}


def get_adapter_class(protocol_type: str):
	adapter_class = DEVICE_ADAPTERS.get(protocol_type)
	if not adapter_class:
		raise AdapterError(f"Unsupported protocol type: {protocol_type!r}", error_code="NOT_SUPPORTED")
	return adapter_class


def create_adapter(device, credential=None):
	"""device: Attendance Device document (or dict-like with
	.get("protocol_type"))."""
	adapter_class = get_adapter_class(device.get("protocol_type"))
	return adapter_class(device, credential)


def get_adapter_for_device(device, credential=None):
	"""The actual entry point everything else in the app should use.

	Branches on Connection Mode: "Local Agent" devices (ERPNext remote
	from the device's network) get a RemoteAgentAdapter that relays every
	call through the agent over HTTP; "Server" devices (the default) get
	the normal direct adapter from create_adapter(). Either way the
	caller sees the identical AttendanceDeviceAdapter interface.
	"""
	if (device.get("connection_mode") or "Server") == "Local Agent":
		from attendance_device_integration.device_adapters.remote_agent_adapter import RemoteAgentAdapter
		return RemoteAgentAdapter(device, credential)
	return create_adapter(device, credential)
