"""Creates the 10 Query Reports. All are plain SQL against this app's own
tables (no user input is ever concatenated into the query), filterable
from the standard Report view."""

import frappe

MODULE = "Attendance Device Integration"


def make_report(name, ref_doctype, query, roles=("Attendance Integration Manager", "Attendance Integration User")):
	if frappe.db.exists("Report", name):
		print(f"  - Report already exists, skipping: {name}")
		return
	frappe.get_doc({
		"doctype": "Report",
		"report_name": name,
		"ref_doctype": ref_doctype,
		"report_type": "Query Report",
		"is_standard": "Yes",
		"module": MODULE,
		"query": query.strip(),
		"roles": [{"role": r} for r in roles],
	}).insert(ignore_permissions=True)
	print(f"  + Created Report: {name}")


def execute():
	frappe.set_user("Administrator")

	make_report(
		"Attendance Device Status",
		"Attendance Device",
		"""
		SELECT
			name AS "Device:Link/Attendance Device:200",
			protocol_type AS "Protocol:Data:160",
			device_brand AS "Brand:Data:120",
			enabled AS "Enabled:Check:80",
			last_sync_status AS "Last Sync Status:Data:140",
			last_sync_datetime AS "Last Sync:Datetime:160",
			last_successful_sync AS "Last Successful Sync:Datetime:160",
			last_sync_message AS "Message:Data:250"
		FROM `tabAttendance Device`
		ORDER BY last_sync_datetime DESC
		""",
	)

	make_report(
		"Attendance Sync Log Summary",
		"Attendance Sync Log",
		"""
		SELECT
			device AS "Device:Link/Attendance Device:180",
			sync_type AS "Sync Type:Data:120",
			status AS "Status:Data:100",
			sync_started_at AS "Started:Datetime:160",
			sync_completed_at AS "Completed:Datetime:160",
			records_fetched AS "Fetched:Int:90",
			records_inserted AS "Inserted:Int:90",
			records_duplicated AS "Duplicates:Int:90",
			records_failed AS "Failed:Int:90",
			error_message AS "Error:Data:250"
		FROM `tabAttendance Sync Log`
		ORDER BY sync_started_at DESC
		""",
	)

	make_report(
		"Attendance Raw Logs",
		"Attendance Raw Log",
		"""
		SELECT
			name AS "Log:Link/Attendance Raw Log:140",
			device AS "Device:Link/Attendance Device:160",
			device_user_id AS "Device User ID:Data:120",
			employee AS "Employee:Link/Employee:160",
			punch_datetime AS "Punch Datetime:Datetime:160",
			direction AS "Direction:Data:90",
			processing_status AS "Status:Data:140",
			source AS "Source:Data:100"
		FROM `tabAttendance Raw Log`
		ORDER BY punch_datetime DESC
		""",
	)

	make_report(
		"Unmapped Device Employees",
		"Attendance Raw Log",
		"""
		SELECT
			device AS "Device:Link/Attendance Device:180",
			device_user_id AS "Device User ID:Data:150",
			COUNT(*) AS "Unmapped Punches:Int:140",
			MIN(punch_datetime) AS "First Seen:Datetime:160",
			MAX(punch_datetime) AS "Last Seen:Datetime:160"
		FROM `tabAttendance Raw Log`
		WHERE processing_status = 'Unmapped Employee'
		GROUP BY device, device_user_id
		ORDER BY "Unmapped Punches:Int:140" DESC
		""",
	)

	make_report(
		"Failed Attendance Logs",
		"Attendance Raw Log",
		"""
		SELECT
			name AS "Log:Link/Attendance Raw Log:140",
			device AS "Device:Link/Attendance Device:160",
			device_user_id AS "Device User ID:Data:120",
			employee AS "Employee:Link/Employee:160",
			punch_datetime AS "Punch Datetime:Datetime:160",
			processing_message AS "Error:Data:300"
		FROM `tabAttendance Raw Log`
		WHERE processing_status = 'Error'
		ORDER BY punch_datetime DESC
		""",
	)

	make_report(
		"Duplicate Attendance Logs",
		"Attendance Sync Log",
		"""
		SELECT
			device AS "Device:Link/Attendance Device:180",
			sync_type AS "Sync Type:Data:120",
			sync_started_at AS "Sync Started:Datetime:160",
			records_duplicated AS "Duplicates Skipped:Int:150",
			records_fetched AS "Total Fetched:Int:130"
		FROM `tabAttendance Sync Log`
		WHERE records_duplicated > 0
		ORDER BY sync_started_at DESC
		""",
	)

	make_report(
		"Daily Device Attendance",
		"Attendance Raw Log",
		"""
		SELECT
			punch_date AS "Date:Date:120",
			device AS "Device:Link/Attendance Device:180",
			COUNT(*) AS "Total Punches:Int:120",
			SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END) AS "IN:Int:80",
			SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END) AS "OUT:Int:80",
			SUM(CASE WHEN processing_status = 'Unmapped Employee' THEN 1 ELSE 0 END) AS "Unmapped:Int:100"
		FROM `tabAttendance Raw Log`
		GROUP BY punch_date, device
		ORDER BY punch_date DESC
		""",
	)

	make_report(
		"Employee Punch Report",
		"Attendance Raw Log",
		"""
		SELECT
			employee AS "Employee:Link/Employee:160",
			employee_number AS "Employee Number:Data:130",
			device AS "Device:Link/Attendance Device:160",
			punch_datetime AS "Punch Datetime:Datetime:160",
			direction AS "Direction:Data:90",
			verification_type AS "Verification:Data:120"
		FROM `tabAttendance Raw Log`
		WHERE employee IS NOT NULL AND employee != ''
		ORDER BY punch_datetime DESC
		""",
	)

	make_report(
		"Device-wise Attendance",
		"Attendance Raw Log",
		"""
		SELECT
			device AS "Device:Link/Attendance Device:180",
			COUNT(*) AS "Total Logs:Int:110",
			SUM(CASE WHEN processing_status = 'Processed' THEN 1 ELSE 0 END) AS "Processed:Int:100",
			SUM(CASE WHEN processing_status = 'Unmapped Employee' THEN 1 ELSE 0 END) AS "Unmapped:Int:100",
			SUM(CASE WHEN processing_status = 'Error' THEN 1 ELSE 0 END) AS "Failed:Int:90",
			SUM(CASE WHEN processing_status = 'Pending' THEN 1 ELSE 0 END) AS "Pending:Int:90"
		FROM `tabAttendance Raw Log`
		GROUP BY device
		ORDER BY "Total Logs:Int:110" DESC
		""",
	)

	make_report(
		"Sync Exception Report",
		"Attendance Sync Log",
		"""
		SELECT
			'Sync' AS "Exception Type:Data:100",
			device AS "Device:Link/Attendance Device:180",
			status AS "Status:Data:100",
			sync_started_at AS "When:Datetime:160",
			error_message AS "Details:Data:300"
		FROM `tabAttendance Sync Log`
		WHERE status IN ('Failed', 'Partial')

		UNION ALL

		SELECT
			'Raw Log' AS "Exception Type:Data:100",
			device AS "Device:Link/Attendance Device:180",
			processing_status AS "Status:Data:100",
			punch_datetime AS "When:Datetime:160",
			processing_message AS "Details:Data:300"
		FROM `tabAttendance Raw Log`
		WHERE processing_status IN ('Error', 'Unmapped Employee', 'Invalid Datetime')

		ORDER BY "When:Datetime:160" DESC
		""",
	)

	frappe.db.commit()
	print("Done.")
