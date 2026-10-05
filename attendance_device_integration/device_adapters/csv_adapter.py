"""CSV import adapter - reads the file attached on the Attendance Device
(import_file) using the column mapping configured there."""

from __future__ import annotations

import csv

import frappe

from attendance_device_integration.device_adapters.base import AdapterError
from attendance_device_integration.device_adapters.file_import_base import FileImportAdapterBase


class CSVAdapter(FileImportAdapterBase):
	adapter_name = "CSV Import"

	def _rows(self):
		file_url = self.device.get("import_file")
		try:
			file_path = frappe.utils.file_manager.get_file_path(file_url)
		except Exception as e:
			raise AdapterError(f"Could not resolve import file: {e}", error_code="INVALID_CONFIG")

		with open(file_path, newline="", encoding="utf-8-sig") as f:
			yield from csv.DictReader(f)
