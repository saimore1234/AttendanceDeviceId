import frappe


def execute():
	frappe.set_user("Administrator")

	doc = frappe.get_doc("DocType", "Attendance Integration Settings")
	for f in doc.fields:
		if f.fieldname == "auto_match_rule":
			f.options = "Attendance Device ID (Employee field)\nEmployee ID\nEmployee Number\nCustom Field"
			f.default = "Attendance Device ID (Employee field)"
			f.description = (
				'"Attendance Device ID" is the standard HRMS Employee field (Attendance & '
				"Leaves tab) built for exactly this - maintain the device's user ID directly "
				"on the Employee master and mapping is automatic."
			)
	doc.save(ignore_permissions=True)

	settings = frappe.get_single("Attendance Integration Settings")
	if settings.auto_match_rule == "Employee Number":
		# Only move it if it's still sitting at the old default - don't
		# clobber an administrator's deliberate choice.
		settings.auto_match_rule = "Attendance Device ID (Employee field)"
		settings.save(ignore_permissions=True)
		print("Updated Settings.auto_match_rule to the new default")
	else:
		print(f"Settings.auto_match_rule left as-is: {settings.auto_match_rule!r}")

	frappe.db.commit()
	print("Done.")
