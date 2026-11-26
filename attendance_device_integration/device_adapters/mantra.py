
from attendance_device_integration.device_adapters.base import (
    AttendanceDeviceAdapter,
    AdapterError,
)


class MantraAdapter(AttendanceDeviceAdapter):
    adapter_name = "Mantra BioTime SDK"

    def connect(self):
        """
        Mantra devices communicate through the Windows BioTime SDK receiver.
        Linux ERPNext does not connect directly to the biometric device.
        """

        self._connected = False

        device_name = getattr(self.device, "name", "Unknown")

        raise AdapterError(
            f"Mantra device {device_name} requires the Windows BioTime SDK "
            "receiver. Direct device connection is unavailable. "
            "Start and configure the Windows receiver before testing.",
            error_code="RECEIVER_OFFLINE",
        )

    def disconnect(self):
        self._connected = False
        return True
