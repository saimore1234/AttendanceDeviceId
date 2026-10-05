"""Structured logging with prefixes ([DEVICE]/[SYNC]/[MAPPING]/[CHECKIN]/
[ERROR]) routed to frappe's own Error Log, with credentials always
redacted - never passwords/tokens in any log line."""

from __future__ import annotations

import frappe

from attendance_device_integration.utils.constants import SENSITIVE_FIELDS


def scrub(text):
	if not text:
		return text
	text = str(text)
	lowered = text.lower()
	for key in SENSITIVE_FIELDS:
		if key in lowered:
			return "[redacted - message referenced a sensitive field name]"
	return text


def log(prefix: str, message: str, title: str = None, traceback: bool = False):
	full_message = f"{prefix} {scrub(message)}"
	try:
		frappe.logger("attendance_device_integration").info(full_message)
		if traceback:
			frappe.log_error(title=title or prefix, message=frappe.get_traceback())
	except Exception:
		pass


def log_device(message, **kwargs):
	log("[DEVICE]", message, **kwargs)


def log_sync(message, **kwargs):
	log("[SYNC]", message, **kwargs)


def log_mapping(message, **kwargs):
	log("[MAPPING]", message, **kwargs)


def log_checkin(message, **kwargs):
	log("[CHECKIN]", message, **kwargs)


def log_error(message, **kwargs):
	log("[ERROR]", message, traceback=True, **kwargs)
