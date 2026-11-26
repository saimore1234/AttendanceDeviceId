
from attendance_device_integration.device_adapters.base import (
    AttendanceDeviceAdapter,
    AdapterError,
)


class MantraAdapter(AttendanceDeviceAdapter):
    adapter_name = "Mantra BioTime SDK"

    def connect(self):
        raise AdapterError(
            "Mantra devices use the Windows BioTime SDK receiver. "
            "Direct Linux SDK communication is not supported.",
            error_code="RECEIVER_REQUIRED",
        )

    def disconnect(self):
        self._connected = False
