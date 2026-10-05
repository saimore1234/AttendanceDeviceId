import frappe


def execute():
	reports = frappe.get_all("Report", filters={"module": "Attendance Device Integration"}, fields=["name", "query"])
	print(f"Found {len(reports)} reports")

	for r in reports:
		try:
			rows = frappe.db.sql(r.query)
			print(f"  OK  {r.name}: {len(rows)} row(s)")
		except Exception as e:
			print(f"  FAIL {r.name}: {e}")
