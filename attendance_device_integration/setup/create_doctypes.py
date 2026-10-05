"""
One-off setup script that creates every DocType required by the
Attendance Device Integration app.

Run via:
	bench --site <site> execute attendance_device_integration.setup.create_doctypes.execute

Relies on developer_mode=1 so inserting a "DocType" document also exports
its .json/.py/.js files to disk, same as creating one from the desk UI.

Idempotent: re-running skips any DocType/Role that already exists.
"""

import itertools

import frappe

MODULE = "Attendance Device Integration"

_break_counter = itertools.count(1)


def _col(label):
	return {"fieldname": f"column_break_{next(_break_counter)}", "fieldtype": "Column Break", "label": label}


def _section(label, depends_on=None):
	d = {"fieldname": f"section_break_{next(_break_counter)}", "fieldtype": "Section Break", "label": label}
	if depends_on:
		d["depends_on"] = depends_on
	return d


def make_role(role_name):
	if frappe.db.exists("Role", role_name):
		return
	frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(ignore_permissions=True)


def default_perms(admin_roles=("System Manager", "Attendance Integration Manager"), extra_roles=None):
	perms = []
	for role in admin_roles:
		perms.append({
			"role": role, "read": 1, "write": 1, "create": 1, "delete": 1,
			"report": 1, "export": 1, "print": 1, "email": 1, "share": 1,
		})
	for role, rights in (extra_roles or {}).items():
		# IMPORTANT: DocPerm's own field schema defaults read/write/create/
		# delete/report/export/print/email/share to 1 (checked) - any key
		# left unset here would silently grant it, not deny it. Always
		# start from an explicit all-zero row.
		row = {
			"role": role, "read": 0, "write": 0, "create": 0, "delete": 0,
			"report": 0, "export": 0, "print": 0, "email": 0, "share": 0,
		}
		row.update(rights)
		perms.append(row)
	return perms


def make_doctype(name, fields, permissions, autoname=None, issingle=0, track_changes=0,
				  title_field=None, sort_field="modified", sort_order="DESC"):
	if frappe.db.exists("DocType", name):
		print(f"  - DocType already exists, skipping: {name}")
		return

	doc = frappe.get_doc({
		"doctype": "DocType",
		"name": name,
		"module": MODULE,
		"custom": 0,
		"issingle": issingle,
		"track_changes": track_changes,
		"sort_field": sort_field,
		"sort_order": sort_order,
		"fields": fields,
		"permissions": permissions,
	})
	if autoname:
		doc.autoname = autoname
	if title_field:
		doc.title_field = title_field

	doc.insert(ignore_permissions=True)
	print(f"  + Created DocType: {name}")


PROTOCOL_TYPE_OPTIONS = (
	"Generic TCP/IP\nESSL TCP/IP\nZKTeco Compatible TCP/IP\nGeneric HTTP API\n"
	"ADMS\nCSV Import\nExcel Import\nManual Entry"
)


def attendance_device_fields():
	return [
		{"fieldname": "device_name", "fieldtype": "Data", "label": "Device Name", "reqd": 1, "unique": 1, "in_list_view": 1},
		{"fieldname": "enabled", "fieldtype": "Check", "label": "Enabled", "default": "1", "in_list_view": 1},
		{"fieldname": "protocol_type", "fieldtype": "Select", "label": "Protocol / Adapter Type",
		 "options": PROTOCOL_TYPE_OPTIONS, "reqd": 1, "in_list_view": 1,
		 "description": "Determines which device adapter handles this device. Brand/Model below are informational only."},
		_col("Identification"),
		{"fieldname": "device_brand", "fieldtype": "Data", "label": "Device Brand", "in_list_view": 1,
		 "description": "Free text - e.g. ESSL, ZKTeco, Suprema. Never used to select code."},
		{"fieldname": "device_model", "fieldtype": "Data", "label": "Device Model"},
		{"fieldname": "device_id", "fieldtype": "Data", "label": "Device ID",
		 "description": "The ID the device itself uses (not this document's name)"},
		{"fieldname": "serial_number", "fieldtype": "Data", "label": "Serial Number"},
		{"fieldname": "device_type", "fieldtype": "Select", "label": "Device Type",
		 "options": "Biometric\nFace Recognition\nFingerprint\nRFID\nPIN\nFace + Fingerprint\nMulti-Modal\nOther"},
		_col("Connection Mode"),
		{"fieldname": "connection_mode", "fieldtype": "Select", "label": "Connection Mode",
		 "options": "Server\nLocal Agent", "default": "Server",
		 "description": "Server: ERPNext connects to the device directly. Local Agent: a small "
						 "agent running on the device's own network relays the connection - use "
						 "this when ERPNext is remote from the device."},
		{"fieldname": "local_agent_url", "fieldtype": "Data", "label": "Local Agent URL",
		 "depends_on": "eval:doc.connection_mode=='Local Agent'",
		 "description": "e.g. http://<agent-host>:8585 - the agent's own token is stored on "
						 "this device's Attendance Device Credential (Bearer Token)."},

		_section("TCP/IP Settings", depends_on="eval:['Generic TCP/IP','ESSL TCP/IP','ZKTeco Compatible TCP/IP'].includes(doc.protocol_type)"),
		{"fieldname": "ip_address", "fieldtype": "Data", "label": "IP Address"},
		{"fieldname": "port", "fieldtype": "Int", "label": "Port", "default": "4370"},
		_col("TCP/IP Settings (cont.)"),
		{"fieldname": "tcp_device_id", "fieldtype": "Int", "label": "Device ID (Protocol)", "default": "1",
		 "description": "Numeric device/communication ID some TCP protocols require"},
		{"fieldname": "connection_timeout", "fieldtype": "Int", "label": "Connection Timeout (s)", "default": "10"},

		_section("HTTP API Settings", depends_on="eval:doc.protocol_type=='Generic HTTP API'"),
		{"fieldname": "base_url", "fieldtype": "Data", "label": "Base URL"},
		{"fieldname": "http_api_endpoint", "fieldtype": "Data", "label": "Attendance Endpoint"},
		{"fieldname": "http_method", "fieldtype": "Select", "label": "Request Method", "options": "GET\nPOST\nPUT", "default": "GET"},
		_col("HTTP API Settings (cont.)"),
		{"fieldname": "authentication_type", "fieldtype": "Select", "label": "Authentication Type",
		 "options": "None\nBasic\nAPI Key\nBearer Token", "default": "None"},
		{"fieldname": "http_headers", "fieldtype": "Code", "label": "Extra Headers (JSON)", "options": "JSON"},
		{"fieldname": "ssl_verification", "fieldtype": "Check", "label": "SSL Verification", "default": "1"},
		{"fieldname": "http_response_mapping", "fieldtype": "Code", "label": "Response Field Mapping (JSON)", "options": "JSON",
		 "description": 'e.g. {"device_user_id": "data.user_id", "punch_datetime": "data.timestamp", '
						'"punch_type": "data.status", "transaction_id": "data.id", "direction": "data.direction"}'},

		_section("ADMS Settings", depends_on="eval:doc.protocol_type=='ADMS'"),
		{"fieldname": "adms_push_pull_mode", "fieldtype": "Select", "label": "Mode", "options": "Push\nPull", "default": "Push"},
		{"fieldname": "adms_attendance_endpoint", "fieldtype": "Data", "label": "Attendance Endpoint"},
		_col("ADMS Settings (cont.)"),
		{"fieldname": "adms_user_endpoint", "fieldtype": "Data", "label": "User Endpoint"},

		_section("CSV / Excel Import Settings", depends_on="eval:['CSV Import','Excel Import'].includes(doc.protocol_type)"),
		{"fieldname": "import_file", "fieldtype": "Attach", "label": "Import File"},
		{"fieldname": "import_employee_id_column", "fieldtype": "Data", "label": "Employee/Device User ID Column"},
		{"fieldname": "import_datetime_column", "fieldtype": "Data", "label": "Combined Datetime Column"},
		{"fieldname": "import_date_column", "fieldtype": "Data", "label": "Date Column (if separate)"},
		_col("CSV / Excel Import Settings (cont.)"),
		{"fieldname": "import_time_column", "fieldtype": "Data", "label": "Time Column (if separate)"},
		{"fieldname": "import_punch_type_column", "fieldtype": "Data", "label": "Punch Type Column"},
		{"fieldname": "import_direction_column", "fieldtype": "Data", "label": "Direction Column"},
		{"fieldname": "import_date_format", "fieldtype": "Data", "label": "Date Format", "default": "%Y-%m-%d"},
		{"fieldname": "import_time_format", "fieldtype": "Data", "label": "Time Format", "default": "%H:%M:%S"},

		_section("Sync Behaviour"),
		{"fieldname": "auto_sync_enabled", "fieldtype": "Check", "label": "Auto Sync Enabled", "default": "0"},
		{"fieldname": "sync_interval", "fieldtype": "Int", "label": "Sync Interval (minutes)", "default": "5",
		 "depends_on": "eval:doc.auto_sync_enabled"},
		{"fieldname": "punch_pairing_mode", "fieldtype": "Select", "label": "Punch Pairing Mode",
		 "options": "Use Device Direction\nSequential IN/OUT", "default": "Use Device Direction"},
		_col("Sync Behaviour (cont.)"),
		{"fieldname": "clear_logs_after_sync", "fieldtype": "Check", "label": "Clear Device Logs After Sync", "default": "0",
		 "description": "Never enabled by default - clearing device memory is destructive"},
		{"fieldname": "retry_count", "fieldtype": "Int", "label": "Retry Count", "default": "3"},

		_section("Sync Status", depends_on="eval:!doc.__islocal"),
		{"fieldname": "last_sync_datetime", "fieldtype": "Datetime", "label": "Last Sync Datetime", "read_only": 1},
		{"fieldname": "last_successful_sync", "fieldtype": "Datetime", "label": "Last Successful Sync", "read_only": 1},
		{"fieldname": "last_sync_status", "fieldtype": "Select", "label": "Last Sync Status", "read_only": 1,
		 "options": "Never Synced\nSuccess\nPartial\nFailed\nOffline", "default": "Never Synced", "in_list_view": 1},
		_col("Sync Status (cont.)"),
		{"fieldname": "last_sync_message", "fieldtype": "Small Text", "label": "Last Sync Message", "read_only": 1},
		{"fieldname": "last_connection_test", "fieldtype": "Datetime", "label": "Last Connection Test", "read_only": 1},

		_section("Other"),
		{"fieldname": "location", "fieldtype": "Data", "label": "Location"},
		{"fieldname": "company", "fieldtype": "Link", "label": "Company", "options": "Company"},
		{"fieldname": "branch", "fieldtype": "Link", "label": "Branch", "options": "Branch"},
		_col("Other (cont.)"),
		{"fieldname": "device_timezone", "fieldtype": "Data", "label": "Device Timezone", "default": "Asia/Kolkata",
		 "description": "IANA timezone name, e.g. Asia/Kolkata, America/New_York"},
		{"fieldname": "notes", "fieldtype": "Small Text", "label": "Notes"},
	]


def attendance_device_credential_fields():
	return [
		{"fieldname": "device", "fieldtype": "Link", "label": "Device", "options": "Attendance Device", "reqd": 1, "unique": 1, "in_list_view": 1},
		{"fieldname": "username", "fieldtype": "Data", "label": "Username"},
		{"fieldname": "password", "fieldtype": "Password", "label": "Password"},
		_col("Credentials (cont.)"),
		{"fieldname": "api_key", "fieldtype": "Password", "label": "API Key"},
		{"fieldname": "bearer_token", "fieldtype": "Password", "label": "Bearer Token"},
		{"fieldname": "certificate", "fieldtype": "Attach", "label": "Certificate"},
	]


def attendance_device_mapping_fields():
	return [
		{"fieldname": "device", "fieldtype": "Link", "label": "Device", "options": "Attendance Device", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
		{"fieldname": "device_user_id", "fieldtype": "Data", "label": "Device User ID", "reqd": 1, "in_list_view": 1, "search_index": 1},
		{"fieldname": "active", "fieldtype": "Check", "label": "Active", "default": "1", "in_list_view": 1},
		_col("Employee"),
		{"fieldname": "employee", "fieldtype": "Link", "label": "Employee", "options": "Employee", "in_list_view": 1},
		{"fieldname": "employee_number", "fieldtype": "Data", "label": "Employee Number", "fetch_from": "employee.employee_number", "read_only": 1},
		{"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name", "fetch_from": "employee.employee_name", "read_only": 1},
	]


def attendance_raw_log_fields():
	return [
		{"fieldname": "device", "fieldtype": "Link", "label": "Device", "options": "Attendance Device", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
		{"fieldname": "device_user_id", "fieldtype": "Data", "label": "Device User ID", "in_list_view": 1, "search_index": 1},
		{"fieldname": "punch_datetime", "fieldtype": "Datetime", "label": "Punch Datetime", "reqd": 1, "in_list_view": 1, "search_index": 1},
		_col("Employee"),
		{"fieldname": "employee", "fieldtype": "Link", "label": "Employee", "options": "Employee", "in_list_view": 1},
		{"fieldname": "employee_number", "fieldtype": "Data", "label": "Employee Number"},
		{"fieldname": "processing_status", "fieldtype": "Select", "label": "Processing Status", "in_list_view": 1,
		 "in_standard_filter": 1, "search_index": 1,
		 "options": "Pending\nProcessed\nUnmapped Employee\nDuplicate\nInvalid Datetime\nError", "default": "Pending"},

		_section("Punch Details"),
		{"fieldname": "punch_date", "fieldtype": "Date", "label": "Punch Date", "read_only": 1},
		{"fieldname": "punch_time", "fieldtype": "Time", "label": "Punch Time", "read_only": 1},
		{"fieldname": "punch_type", "fieldtype": "Data", "label": "Punch Type (raw)"},
		{"fieldname": "direction", "fieldtype": "Select", "label": "Direction", "options": "IN\nOUT\nUNKNOWN", "default": "UNKNOWN"},
		_col("Punch Details (cont.)"),
		{"fieldname": "verification_type", "fieldtype": "Data", "label": "Verification Type"},
		{"fieldname": "work_code", "fieldtype": "Data", "label": "Work Code"},
		{"fieldname": "transaction_id", "fieldtype": "Data", "label": "Transaction ID"},
		{"fieldname": "device_transaction_id", "fieldtype": "Data", "label": "Device Transaction ID", "search_index": 1},

		_section("Processing"),
		{"fieldname": "source", "fieldtype": "Select", "label": "Source",
		 "options": "Sync\nWebhook\nManual Import\nCSV\nExcel", "default": "Sync"},
		{"fieldname": "processed", "fieldtype": "Check", "label": "Processed", "default": "0"},
		{"fieldname": "processing_message", "fieldtype": "Small Text", "label": "Processing Message"},
		_col("Processing (cont.)"),
		{"fieldname": "unique_hash", "fieldtype": "Data", "label": "Unique Hash", "unique": 1, "read_only": 1},
		{"fieldname": "received_at", "fieldtype": "Datetime", "label": "Received At", "default": "now", "read_only": 1},
		{"fieldname": "employee_checkin", "fieldtype": "Link", "label": "Employee Checkin", "options": "Employee Checkin", "read_only": 1},

		_section("Raw Data"),
		{"fieldname": "raw_data", "fieldtype": "Code", "label": "Raw Data", "read_only": 1},
	]


def attendance_sync_log_fields():
	return [
		{"fieldname": "device", "fieldtype": "Link", "label": "Device", "options": "Attendance Device", "in_list_view": 1, "in_standard_filter": 1},
		{"fieldname": "sync_type", "fieldtype": "Select", "label": "Sync Type", "in_list_view": 1,
		 "options": "Manual\nScheduled\nInitial Sync\nIncremental Sync\nFull Sync"},
		{"fieldname": "status", "fieldtype": "Select", "label": "Status", "in_list_view": 1, "in_standard_filter": 1,
		 "options": "Running\nSuccess\nPartial\nFailed"},
		_col("Timing"),
		{"fieldname": "start_datetime", "fieldtype": "Datetime", "label": "Fetch Window Start"},
		{"fieldname": "end_datetime", "fieldtype": "Datetime", "label": "Fetch Window End"},
		{"fieldname": "sync_started_at", "fieldtype": "Datetime", "label": "Sync Started At"},
		{"fieldname": "sync_completed_at", "fieldtype": "Datetime", "label": "Sync Completed At"},

		_section("Results"),
		{"fieldname": "records_fetched", "fieldtype": "Int", "label": "Records Fetched", "default": "0"},
		{"fieldname": "records_inserted", "fieldtype": "Int", "label": "Records Inserted", "default": "0"},
		{"fieldname": "records_duplicated", "fieldtype": "Int", "label": "Records Duplicated", "default": "0"},
		_col("Results (cont.)"),
		{"fieldname": "records_processed", "fieldtype": "Int", "label": "Records Processed", "default": "0"},
		{"fieldname": "records_failed", "fieldtype": "Int", "label": "Records Failed", "default": "0"},

		_section("Error"),
		{"fieldname": "error_message", "fieldtype": "Small Text", "label": "Error Message"},
	]


def attendance_integration_settings_fields():
	return [
		{"fieldname": "enable_integration", "fieldtype": "Check", "label": "Enable Integration", "default": "1"},
		{"fieldname": "enable_background_sync", "fieldtype": "Check", "label": "Enable Background Sync", "default": "1"},
		_col("Defaults"),
		{"fieldname": "default_company", "fieldtype": "Link", "label": "Default Company", "options": "Company"},
		{"fieldname": "default_timezone", "fieldtype": "Data", "label": "Default Timezone", "default": "Asia/Kolkata"},
		{"fieldname": "default_sync_interval", "fieldtype": "Int", "label": "Default Sync Interval (minutes)", "default": "5"},

		_section("Attendance Creation"),
		{"fieldname": "create_employee_checkin", "fieldtype": "Check", "label": "Create Employee Checkin", "default": "1"},
		{"fieldname": "create_attendance", "fieldtype": "Check", "label": "Create Attendance Directly", "default": "0",
		 "description": "Not recommended - prefer letting HRMS shift processing build Attendance from Employee Checkin"},
		_col("Attendance Creation (cont.)"),
		{"fieldname": "punch_pairing_mode", "fieldtype": "Select", "label": "Default Punch Pairing Mode",
		 "options": "Use Device Direction\nSequential IN/OUT", "default": "Use Device Direction"},

		_section("Employee Mapping"),
		{"fieldname": "auto_match_rule", "fieldtype": "Select", "label": "Auto Match Device User ID To",
		 "options": "Attendance Device ID (Employee field)\nEmployee ID\nEmployee Number\nCustom Field",
		 "default": "Attendance Device ID (Employee field)",
		 "description": "\"Attendance Device ID\" is the standard HRMS Employee field "
						 "(Attendance & Leaves tab) built for exactly this - maintain the "
						 "device's user ID directly on the Employee master and mapping is automatic."},
		{"fieldname": "auto_match_custom_field", "fieldtype": "Data", "label": "Custom Employee Field",
		 "depends_on": "eval:doc.auto_match_rule=='Custom Field'"},
		_col("Employee Mapping (cont.)"),
		{"fieldname": "create_missing_employees", "fieldtype": "Check", "label": "Allow Creating Missing Employees", "default": "0"},

		_section("Duplicate Handling & Retry"),
		{"fieldname": "duplicate_handling", "fieldtype": "Select", "label": "Duplicate Handling",
		 "options": "Skip\nLog Only\nOverwrite", "default": "Skip"},
		{"fieldname": "error_retry_count", "fieldtype": "Int", "label": "Error Retry Count", "default": "3"},
		_col("Duplicate Handling & Retry (cont.)"),
		{"fieldname": "time_difference_warning_threshold", "fieldtype": "Int",
		 "label": "Time Diff Warning Threshold (s)", "default": "300"},

		_section("Performance"),
		{"fieldname": "batch_size", "fieldtype": "Int", "label": "Batch Size", "default": "500"},
		{"fieldname": "api_timeout", "fieldtype": "Int", "label": "API Timeout (s)", "default": "10"},
		_col("Performance (cont.)"),
		{"fieldname": "log_retention_days", "fieldtype": "Int", "label": "Log Retention (days)", "default": "0",
		 "description": "0 = keep forever"},
	]


def attendance_device_command_log_fields():
	return [
		{"fieldname": "device", "fieldtype": "Link", "label": "Device", "options": "Attendance Device", "in_list_view": 1, "in_standard_filter": 1},
		{"fieldname": "command", "fieldtype": "Select", "label": "Command", "in_list_view": 1,
		 "options": "Test Connection\nGet Device Info\nGet Users\nSync Users\nSync Attendance\n"
					"Clear Logs\nSet Time\nGet Time\nRestart Device"},
		{"fieldname": "status", "fieldtype": "Select", "label": "Status", "in_list_view": 1,
		 "options": "Queued\nRunning\nSuccess\nFailed"},
		_col("Who/When"),
		{"fieldname": "requested_by", "fieldtype": "Link", "label": "Requested By", "options": "User", "default": "__user"},
		{"fieldname": "requested_at", "fieldtype": "Datetime", "label": "Requested At", "default": "now"},
		{"fieldname": "completed_at", "fieldtype": "Datetime", "label": "Completed At"},

		_section("Result"),
		{"fieldname": "response", "fieldtype": "Code", "label": "Response"},
		{"fieldname": "error", "fieldtype": "Small Text", "label": "Error"},
	]


def execute():
	frappe.set_user("Administrator")

	print("Creating roles...")
	make_role("Attendance Integration Manager")
	make_role("Attendance Integration User")

	print("Creating DocTypes...")

	make_doctype(
		"Attendance Device",
		attendance_device_fields(),
		default_perms(extra_roles={"Attendance Integration User": {"read": 1}}),
		autoname="field:device_name",
		title_field="device_name",
	)

	make_doctype(
		"Attendance Device Credential",
		attendance_device_credential_fields(),
		default_perms(),  # managers only - never exposed to Integration User
		autoname="field:device",
	)

	make_doctype(
		"Attendance Device Mapping",
		attendance_device_mapping_fields(),
		default_perms(extra_roles={"Attendance Integration User": {"read": 1}}),
		autoname="format:ADM-{#####}",
	)

	make_doctype(
		"Attendance Raw Log",
		attendance_raw_log_fields(),
		default_perms(extra_roles={"Attendance Integration User": {"read": 1}}),
		autoname="format:ARL-{#####}",
		track_changes=1,
	)

	make_doctype(
		"Attendance Sync Log",
		attendance_sync_log_fields(),
		default_perms(extra_roles={"Attendance Integration User": {"read": 1}}),
		autoname="format:ASL-{#####}",
	)

	make_doctype(
		"Attendance Integration Settings",
		attendance_integration_settings_fields(),
		default_perms(extra_roles={"Attendance Integration User": {"read": 1}}),
		issingle=1,
	)

	make_doctype(
		"Attendance Device Command Log",
		attendance_device_command_log_fields(),
		default_perms(extra_roles={"Attendance Integration User": {"read": 1}}),
		autoname="format:ACL-{#####}",
	)

	# Materialize the Settings singleton's declared defaults into the DB -
	# otherwise raw db.get_single_value() reads see None instead of the
	# field's "default" until the record has been saved at least once.
	settings = frappe.get_single("Attendance Integration Settings")
	settings.save(ignore_permissions=True)

	frappe.db.commit()
	print("Done.")
