"""Duplicate detection: a deterministic hash from the fields that
identify a punch uniquely, so the same physical punch never creates two
Attendance Raw Log / Employee Checkin records even if fetched twice
(overlapping sync windows, re-imported CSV, retried webhook, ...)."""

from __future__ import annotations

import hashlib
from datetime import datetime


def compute_unique_hash(device: str, device_user_id: str, punch_datetime: datetime, transaction_id: str = None) -> str:
	parts = [
		str(device or ""),
		str(device_user_id or ""),
		punch_datetime.isoformat() if isinstance(punch_datetime, datetime) else str(punch_datetime or ""),
		str(transaction_id or ""),
	]
	return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
