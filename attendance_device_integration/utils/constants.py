"""Shared constants. Nothing device/vendor-specific lives here."""

PROTOCOL_TYPES = (
	"Generic TCP/IP", "ESSL TCP/IP", "ZKTeco Compatible TCP/IP", "Generic HTTP API",
	"ADMS", "CSV Import", "Excel Import", "Manual Entry",
)

PROCESSING_STATUS_PENDING = "Pending"
PROCESSING_STATUS_PROCESSED = "Processed"
PROCESSING_STATUS_UNMAPPED = "Unmapped Employee"
PROCESSING_STATUS_DUPLICATE = "Duplicate"
PROCESSING_STATUS_INVALID_DATETIME = "Invalid Datetime"
PROCESSING_STATUS_ERROR = "Error"

SYNC_STATUS_RUNNING = "Running"
SYNC_STATUS_SUCCESS = "Success"
SYNC_STATUS_PARTIAL = "Partial"
SYNC_STATUS_FAILED = "Failed"

LAST_SYNC_NEVER = "Never Synced"
LAST_SYNC_SUCCESS = "Success"
LAST_SYNC_PARTIAL = "Partial"
LAST_SYNC_FAILED = "Failed"
LAST_SYNC_OFFLINE = "Offline"

# Fields whose values must never appear in logs/error messages.
SENSITIVE_FIELDS = ("password", "api_key", "bearer_token", "token", "certificate")

LOG_PREFIX_DEVICE = "[DEVICE]"
LOG_PREFIX_SYNC = "[SYNC]"
LOG_PREFIX_MAPPING = "[MAPPING]"
LOG_PREFIX_CHECKIN = "[CHECKIN]"
LOG_PREFIX_ERROR = "[ERROR]"
