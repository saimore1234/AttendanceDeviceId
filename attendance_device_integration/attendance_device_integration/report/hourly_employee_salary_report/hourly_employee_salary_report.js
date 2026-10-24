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
			fieldname: "duplicate_window_minutes",
			label: __("Merge Repeated Scans Within (minutes)"),
			fieldtype: "Int",
			default: 5,
			description: __("Scans closer together than this count as one punch. 0 turns it off."),
		},
		{
			fieldname: "pay_weekly_offs",
			label: __("Pay Weekly Offs to Staff"),
			fieldtype: "Check",
			default: 0,
			description: __("Holidays in the Holiday List are always paid to Staff; tick to include weekly offs (e.g. Sundays) too."),
		},
		{
			fieldname: "ignore_device_log_type",
			label: __("Ignore Machine IN/OUT (pair by punch order)"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_incomplete",
			label: __("Pay Complete Pairs on Incomplete Days"),
			fieldtype: "Check",
			default: 0,
		},
	],

	onload(report) {
		if (!frappe.model.can_create("Salary Slip")) return;
		report.page.add_inner_button(__("Create Salary Slips"), () => open_salary_slip_dialog(report));
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "punch_status" && data && data.punch_status) {
			const color = ["Complete", "Paid Holiday"].includes(data.punch_status)
				? "green"
				: data.punch_status === "Holiday"
					? "blue"
					: "red";
			value = `<span style="color: var(--${color}-600)">${value}</span>`;
		}
		return value;
	},
};

const PUNCH_SALARY_API = "attendance_device_integration.api.punch_salary";

function open_salary_slip_dialog(report) {
	const filters = report.get_values();
	if (!filters.from_date || !filters.to_date) {
		frappe.msgprint(__("Set From Date and To Date first"));
		return;
	}

	frappe.call({
		method: `${PUNCH_SALARY_API}.preview`,
		args: { filters },
		freeze: true,
		freeze_message: __("Calculating..."),
		callback({ message: rows }) {
			if (!rows || !rows.length) {
				frappe.msgprint(__("No employees with punches in this period"));
				return;
			}
			show_salary_slip_dialog(filters, rows);
		},
	});
}

function show_salary_slip_dialog(filters, rows) {
	const body = rows
		.map(
			(r) => `<tr>
				<td><input type="checkbox" class="slip-check" data-employee="${frappe.utils.escape_html(r.employee)}"
					${r.will_create ? "checked" : "disabled"}></td>
				<td>${frappe.utils.escape_html(r.employee_name || r.employee)}</td>
				<td class="text-right">${format_currency(r.salary)}</td>
				<td style="${r.incomplete_days ? "color: var(--red-600)" : ""}">${frappe.utils.escape_html(r.state)}</td>
			</tr>`
		)
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Create Salary Slips ({0} to {1})", [
			frappe.datetime.str_to_user(filters.from_date),
			frappe.datetime.str_to_user(filters.to_date),
		]),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "preview",
				options: `<p class="text-muted">${__(
					"Draft slips are created from the report amounts; the Salary Structure splits and deducts from them. Review and submit them in Salary Slip."
				)}</p>
				<table class="table table-bordered">
					<thead><tr><th></th><th>${__("Employee")}</th><th class="text-right">${__("Pay")}</th><th>${__("Status")}</th></tr></thead>
					<tbody>${body}</tbody>
				</table>`,
			},
		],
		primary_action_label: __("Create Draft Slips"),
		primary_action() {
			const employees = dialog.$wrapper
				.find(".slip-check:checked")
				.map((_, el) => el.dataset.employee)
				.get();
			if (!employees.length) {
				frappe.msgprint(__("Nothing selected"));
				return;
			}
			frappe.call({
				method: `${PUNCH_SALARY_API}.create_slips`,
				args: { filters, employees },
				freeze: true,
				freeze_message: __("Creating Salary Slips..."),
				callback({ message: res }) {
					dialog.hide();
					show_salary_slip_result(res);
				},
			});
		},
	});
	dialog.show();
}

function show_salary_slip_result(res) {
	const link = (slip) => frappe.utils.get_form_link("Salary Slip", slip, true);
	let html = `<p><b>${__("Created")}: ${res.created.length}</b></p><ul>${res.created
		.map((c) => `<li>${link(c.slip)} - ${frappe.utils.escape_html(c.employee)} (${__("Net")} ${format_currency(c.net_pay)})</li>`)
		.join("")}</ul>`;
	if (res.skipped.length) {
		html += `<p><b>${__("Skipped")}: ${res.skipped.length}</b></p><ul>${res.skipped
			.map((s) => `<li>${frappe.utils.escape_html(s.employee)}: ${frappe.utils.escape_html(s.reason)}</li>`)
			.join("")}</ul>`;
	}
	if (res.failed.length) {
		html += `<p style="color: var(--red-600)"><b>${__("Failed")}: ${res.failed.length}</b></p><ul>${res.failed
			.map((f) => `<li>${frappe.utils.escape_html(f.employee)}: ${frappe.utils.escape_html(f.reason)}</li>`)
			.join("")}</ul>`;
	}
	frappe.msgprint({ title: __("Salary Slips"), message: html, wide: true });
}
