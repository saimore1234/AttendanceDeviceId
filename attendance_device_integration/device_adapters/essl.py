"""ESSL TCP/IP adapter.

ESSL's TCP/IP biometric range commonly ships on ZK-compatible firmware,
so this is a thin, clearly-named subclass of ZKProtocolAdapter rather
than a reimplementation. If a specific ESSL model uses a different,
proprietary protocol, connect()/test_connection() will report a clear
connection/protocol error instead of silently pretending to work - there
is no generic way to support an unknown proprietary protocol, and this
adapter does not claim to.
"""

from attendance_device_integration.device_adapters.zk_protocol import ZKProtocolAdapter


class ESSLAdapter(ZKProtocolAdapter):
	adapter_name = "ESSL TCP/IP (ZK-compatible)"
