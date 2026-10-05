"""Fixes the "Attendance Integration User" DocPerm rows that were
accidentally created with full CRUD access instead of read-only, because
DocPerm's own field schema defaults write/create/delete/report/export/
print/email/share to 1 and the original helper left those keys unset on
rows constructed programmatically (see create_doctypes.py default_perms
fix). Also verifies Attendance Device Credential has NO row for this role
at all (managers only).
"""

import frappe

AFFECTED_DOCTYPES = (
	"Attendance Device",
	"Attendance Device Mapping",
	"Attendance Raw Log",
	"Attendance Sync Log",
	"Attendance Integration Settings",
	"Attendance Device Command Log",
)

ROLE = "Attendance Integration User"


def execute():
	frappe.set_user("Administrator")

	for doctype in AFFECTED_DOCTYPES:
		doc = frappe.get_doc("DocType", doctype)
		changed = False
		for perm in doc.permissions:
			if perm.role != ROLE:
				continue
			before = (perm.read, perm.write, perm.create, perm.delete, perm.report, perm.export, perm.print, perm.email, perm.share)
			perm.read = 1
			perm.write = 0
			perm.create = 0
			perm.delete = 0
			perm.report = 0
			perm.export = 0
			perm.print = 0
			perm.email = 0
			perm.share = 0
			after = (perm.read, perm.write, perm.create, perm.delete, perm.report, perm.export, perm.print, perm.email, perm.share)
			if before != after:
				changed = True
				print(f"{doctype}: {ROLE} permission {before} -> {after}")

		if changed:
			doc.save(ignore_permissions=True)

	# Sanity check: Credential doctype should have no row for this role at all.
	cred = frappe.get_doc("DocType", "Attendance Device Credential")
	has_user_row = any(p.role == ROLE for p in cred.permissions)
	print(f"Attendance Device Credential has a {ROLE} row: {has_user_row} (expected: False)")

	frappe.db.commit()
	print("Done.")
