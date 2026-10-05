"""Shared column-mapping/row-normalization logic for CSV and Excel
adapters. No column names are assumed - the administrator maps them on
the Attendance Device form (import_employee_id_column, etc.)."""

from __future__ import annotations

from datetime import datetime

from attendance_device_integration.device_adapters.base import AdapterError, AttendanceDeviceAdapter, RawPunch


class FileImportAdapterBase(AttendanceDeviceAdapter):
	def connect(self) -> None:
		if not self.device.get("import_file"):
			raise AdapterError("No Import File attached on this device", error_code="INVALID_CONFIG")
		self._connected = True

	def disconnect(self) -> None:
		self._connected = False

	def _rows(self):
		"""Subclasses yield one dict per row: {column_name: value}."""
		raise NotImplementedError

	def get_attendance_logs(self):
		employee_col = self.device.get("import_employee_id_column")
		datetime_col = self.device.get("import_datetime_column")
		date_col = self.device.get("import_date_column")
		time_col = self.device.get("import_time_column")
		punch_type_col = self.device.get("import_punch_type_column")
		direction_col = self.device.get("import_direction_column")
		date_format = self.device.get("import_date_format") or "%Y-%m-%d"
		time_format = self.device.get("import_time_format") or "%H:%M:%S"

		if not employee_col:
			raise AdapterError("Employee/Device User ID Column is not configured", error_code="INVALID_CONFIG")
		if not datetime_col and not (date_col and time_col):
			raise AdapterError(
				"Configure either Combined Datetime Column, or both Date Column and Time Column",
				error_code="INVALID_CONFIG",
			)

		punches = []
		for idx, row in enumerate(self._rows(), start=1):
			device_user_id = row.get(employee_col)
			if device_user_id in (None, ""):
				continue

			try:
				if datetime_col:
					punch_dt = self._parse(row.get(datetime_col), f"{date_format} {time_format}")
				else:
					punch_dt = self._parse(f"{row.get(date_col)} {row.get(time_col)}", f"{date_format} {time_format}")
			except (ValueError, TypeError) as e:
				raise AdapterError(f"Row {idx}: could not parse datetime - {e}", error_code="INVALID_DATETIME")

			punches.append(RawPunch(
				device_user_id=str(device_user_id),
				punch_datetime=punch_dt,
				punch_type=str(row.get(punch_type_col) or "") if punch_type_col else None,
				direction=str(row.get(direction_col) or "UNKNOWN").upper() if direction_col else "UNKNOWN",
				raw=str(row),
			))
		return punches

	@staticmethod
	def _parse(value, fmt):
		if isinstance(value, datetime):
			return value
		return datetime.strptime(str(value).strip(), fmt)
