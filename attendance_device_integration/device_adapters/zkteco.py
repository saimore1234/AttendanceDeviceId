"""ZKTeco-compatible TCP/IP adapter - see zk_protocol.py for the actual
implementation and its honesty caveats. Kept as its own named module/class
so it shows up distinctly in the adapter registry and in error messages."""

from attendance_device_integration.device_adapters.zk_protocol import ZKProtocolAdapter


class ZKTecoAdapter(ZKProtocolAdapter):
	adapter_name = "ZKTeco Compatible TCP/IP"
