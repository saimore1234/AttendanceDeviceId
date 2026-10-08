frappe.query_reports["Hourly Employee Salary Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "employment_type",
			label: __("Employee Type"),
			fieldtype: "Link",
			options: "Employment Type",
		},
		{
			fieldname: "salary_type",
			label: __("Salary Type"),
			fieldtype: "Select",
			options: "\nWorker\nStaff",
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: "Daily\nMonthly\nEmployee",
			default: "Daily",
		},
		{
			fieldname: "include_incomplete",
			label: __("Pay Complete Pairs on Incomplete Days"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "punch_status" && data && data.punch_status) {
			const color = data.punch_status === "Complete" ? "green" : "red";
			value = `<span style="color: var(--${color}-600)">${value}</span>`;
		}
		return value;
	},
};
