// Copyright (c) 2026, AITS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Device", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Test Connection"), () => test_connection(frm));
		frm.add_custom_button(__("Get Device Info"), () => get_device_info(frm));

		frm.add_custom_button(__("Sync Now"), () => sync_device(frm, "Manual"), __("Sync"));
		frm.add_custom_button(__("Sync Today"), () => sync_range(frm, 0), __("Sync"));
		frm.add_custom_button(__("Sync Yesterday"), () => sync_range(frm, 1), __("Sync"));
		frm.add_custom_button(__("Full Sync"), () => sync_device(frm, "Full Sync"), __("Sync"));

		frm.add_custom_button(__("Get Users"), () => get_users(frm), __("Users"));
		frm.add_custom_button(__("Sync Users / Map Employees"), () => sync_users(frm), __("Users"));

		frm.add_custom_button(__("Get Device Time"), () => get_device_time(frm), __("Device"));
		frm.add_custom_button(__("Set Device Time"), () => set_device_time(frm), __("Device"));
		frm.add_custom_button(__("Clear Device Logs"), () => clear_device_logs(frm), __("Device"));
		frm.add_custom_button(__("Restart Device"), () => restart_device(frm), __("Device"));

		frm.add_custom_button(__("Manage Credentials"), () => {
			frappe.set_route("Form", "Attendance Device Credential", frm.doc.name);
		});

		set_status_indicator(frm);
	},
});

function set_status_indicator(frm) {
	const status = frm.doc.last_sync_status;
	const colors = { "Never Synced": "grey", "Success": "green", "Partial": "orange", "Failed": "red", "Offline": "red" };
	frm.dashboard.clear_headline();
	if (status) {
		frm.dashboard.set_headline_alert(
			`<span class="indicator ${colors[status] || "grey"}">${__("Last Sync")}: ${status}` +
			(frm.doc.last_sync_datetime ? ` (${comment_when(frm.doc.last_sync_datetime)})` : "") + `</span>`
		);
	}
}

function test_connection(frm) {
	frappe.call({
		method: "attendance_device_integration.api.devices.test_connection",
		args: { device: frm.doc.name },
		freeze: true,
		freeze_message: __("Testing connection..."),
		callback: (r) => {
			const res = r.message || {};
			if (res.success) {
				frappe.msgprint({
					title: __("Connection Successful"),
					indicator: "green",
					message: `
						<b>${__("Adapter")}:</b> ${res.adapter}<br>
						<b>${__("Elapsed")}:</b> ${res.elapsed_seconds}s<br>
						<b>${__("Capabilities")}:</b>
						<pre>${JSON.stringify(res.capabilities, null, 2)}</pre>
						${res.device_info ? `<b>${__("Device Info")}:</b><pre>${JSON.stringify(res.device_info, null, 2)}</pre>` : ""}
					`,
				});
			} else {
				show_adapter_error(__("Connection Failed"), res);
			}
			frm.reload_doc();
		},
	});
}

function show_adapter_error(title, res) {
	let message = frappe.utils.escape_html(res.error || "Unknown error");
	if (res.error_code === "SDK_MISSING") {
		message = `<b>${__("Missing required library")}:</b><br>${message}`;
	}
	frappe.msgprint({ title, indicator: "red", message });
}

function get_device_info(frm) {
	frappe.call({
		method: "attendance_device_integration.api.devices.get_device_info",
		args: { device: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const res = r.message || {};
			if (res.success) {
				frappe.msgprint({ title: __("Device Info"), indicator: "blue", message: `<pre>${JSON.stringify(res, null, 2)}</pre>` });
			} else {
				show_adapter_error(__("Could Not Get Device Info"), res);
			}
		},
	});
}

function sync_device(frm, sync_type) {
	frappe.call({
		method: "attendance_device_integration.api.devices.sync_device",
		args: { device: frm.doc.name, sync_type: sync_type },
		freeze: true,
		freeze_message: __("Syncing..."),
		callback: (r) => {
			const res = r.message || {};
			if (res.success) {
				frappe.show_alert({
					message: __("Sync complete: {0} fetched, {1} inserted, {2} duplicates, {3} failed",
						[res.fetched, res.inserted, res.duplicated, res.failed]),
					indicator: res.failed ? "orange" : "green",
				});
			} else {
				frappe.msgprint({ title: __("Sync Failed"), indicator: "red", message: res.error });
			}
			frm.reload_doc();
		},
	});
}

function sync_range(frm, days_ago) {
	const date = frappe.datetime.add_days(frappe.datetime.get_today(), -days_ago);
	frappe.call({
		method: "attendance_device_integration.api.devices.sync_device",
		args: { device: frm.doc.name, sync_type: "Manual", start_date: date + " 00:00:00", end_date: date + " 23:59:59" },
		freeze: true,
		freeze_message: __("Syncing..."),
		callback: (r) => {
			const res = r.message || {};
			frappe.show_alert({
				message: res.success
					? __("Sync complete: {0} fetched, {1} inserted", [res.fetched, res.inserted])
					: res.error,
				indicator: res.success ? "green" : "red",
			});
			frm.reload_doc();
		},
	});
}

function get_users(frm) {
	frappe.call({
		method: "attendance_device_integration.api.devices.get_device_users",
		args: { device: frm.doc.name },
		freeze: true,
		freeze_message: __("Fetching users..."),
		callback: (r) => {
			const res = r.message || {};
			if (res.success) {
				frappe.msgprint({
					title: __("Device Users ({0})", [res.users.length]),
					indicator: "blue",
					message: `<pre>${JSON.stringify(res.users, null, 2)}</pre>`,
				});
			} else {
				show_adapter_error(__("Could Not Get Users"), res);
			}
		},
	});
}

function sync_users(frm) {
	frappe.call({
		method: "attendance_device_integration.api.devices.sync_device_users",
		args: { device: frm.doc.name },
		freeze: true,
		freeze_message: __("Syncing users..."),
		callback: (r) => {
			const res = r.message || {};
			if (!res.success) {
				show_adapter_error(__("Could Not Sync Users"), res);
				return;
			}
			frappe.msgprint({
				title: __("User Mapping Status"),
				indicator: res.unmapped.length ? "orange" : "green",
				message: `
					<b>${__("Mapped")}:</b> ${res.mapped.length}<br>
					<b>${__("Unmapped")}:</b> ${res.unmapped.length}
					${res.unmapped.length ? `<pre>${JSON.stringify(res.unmapped.map(u => u.device_user_id), null, 2)}</pre>
					<a href="/app/attendance-device-mapping/new?device=${frm.doc.name}">${__("Create mappings")}</a>` : ""}
				`,
			});
		},
	});
}

function get_device_time(frm) {
	frappe.call({
		method: "attendance_device_integration.api.devices.get_device_time",
		args: { device: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const res = r.message || {};
			if (!res.success) {
				show_adapter_error(__("Could Not Get Device Time"), res);
				return;
			}
			frappe.msgprint({
				title: __("Device Time"),
				indicator: res.warning ? "orange" : "blue",
				message: `
					<b>${__("Device Time")}:</b> ${res.device_time}<br>
					<b>${__("Server Time")}:</b> ${res.server_time}<br>
					<b>${__("Difference")}:</b> ${res.difference_seconds}s
					${res.warning ? `<br><span class="text-danger">${__("Difference exceeds the configured warning threshold")}</span>` : ""}
				`,
			});
		},
	});
}

function set_device_time(frm) {
	frappe.confirm(__("Set the device's clock to match the ERPNext server's current time?"), () => {
		frappe.call({
			method: "attendance_device_integration.api.devices.set_device_time",
			args: { device: frm.doc.name },
			freeze: true,
			callback: (r) => {
				const res = r.message || {};
				if (res.success) frappe.show_alert({ message: __("Device time updated"), indicator: "green" });
				else show_adapter_error(__("Could Not Set Device Time"), res);
			},
		});
	});
}

function clear_device_logs(frm) {
	frappe.confirm(
		__("This permanently deletes attendance logs stored ON THE DEVICE ITSELF. Already-synced data in ERPNext is not affected. Continue?"),
		() => {
			frappe.call({
				method: "attendance_device_integration.api.devices.clear_device_logs",
				args: { device: frm.doc.name, confirm: 1 },
				freeze: true,
				callback: (r) => {
					const res = r.message || {};
					if (res.success) frappe.show_alert({ message: __("Device logs cleared"), indicator: "green" });
					else show_adapter_error(__("Could Not Clear Device Logs"), res);
				},
			});
		}
	);
}

function restart_device(frm) {
	frappe.confirm(__("This will restart the physical device and briefly interrupt it. Continue?"), () => {
		frappe.call({
			method: "attendance_device_integration.api.devices.restart_device",
			args: { device: frm.doc.name, confirm: 1 },
			freeze: true,
			callback: (r) => {
				const res = r.message || {};
				if (res.success) frappe.show_alert({ message: __("Restart command sent"), indicator: "green" });
				else show_adapter_error(__("Could Not Restart Device"), res);
			},
		});
	});
}
