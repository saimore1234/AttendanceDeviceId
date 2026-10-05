"""Loads decrypted credentials for a device. The only place that reads
Attendance Device Credential's Password-type fields in plaintext."""

from __future__ import annotations

import frappe


def load_credential(device_name: str) -> dict:
	if not frappe.db.exists("Attendance Device Credential", device_name):
		return {}
	cred = frappe.get_doc("Attendance Device Credential", device_name)
	return {
		"username": cred.username,
		"password": cred.get_password("password") if cred.password else None,
		"api_key": cred.get_password("api_key") if cred.api_key else None,
		"bearer_token": cred.get_password("bearer_token") if cred.bearer_token else None,
	}
