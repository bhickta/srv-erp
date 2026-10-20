frappe.ui.form.on("SRV Production Schedule", {
	setup(frm) {
		frm.set_query("supervisor", "responsibilities", () => ({
			query: "srv_erp.production.service.supervisor_query",
		}));
		frm.set_query("template", "items", () => ({ filters: { has_variants: 1, disabled: 0 } }));
		frm.set_query("item_code", "items", (doc, cdt, cdn) => ({
			filters: {
				variant_of: locals[cdt][cdn].template || "__select_template_first__",
				has_variants: 0,
				disabled: 0,
			},
		}));
	},
	async start_date(frm) {
		if (frm.doc.docstatus !== 0) return;
		await frm.set_value("schedule_date", frm.doc.start_date);
		return srv_production_update_defaults(frm, "start_date");
	},
	end_date(frm) {
		return srv_production_update_defaults(frm, "end_date");
	},
	frequency(frm) {
		return srv_production_update_defaults(frm, "frequency");
	},
	interval(frm) {
		return srv_production_update_defaults(frm, "interval");
	},
	recurrence_unit(frm) {
		return srv_production_update_defaults(frm, "recurrence_unit");
	},
	weekdays(frm) {
		return srv_production_update_defaults(frm, "weekdays");
	},
	custom_dates(frm) {
		return srv_production_update_defaults(frm, "custom_dates");
	},
	onload(frm) {
		frm._planning_defaults = srv_production_defaults(frm);
	},
	refresh(frm) {
		frm.set_df_property("responsibilities", "read_only", frm.doc.docstatus !== 0);
		frm.set_df_property("items", "read_only", frm.doc.docstatus !== 0);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview Dates"), async () => {
				const { message } = await frm.call("preview");
				const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
				const rows = message.items
					.map(
						(row) => `<tr>
					<td>${escape(row.row)}</td><td>${escape(row.item_code || row.template)}</td>
					<td class="text-nowrap">${escape(row.from_date)}</td><td class="text-nowrap">${escape(row.to_date)}</td>
					<td>${escape(row.frequency)}</td><td>${escape(row.occurrence_count)}</td>
					<td>${escape(row.qty_per_occurrence)}</td><td>${escape(row.planned_qty)} ${escape(row.uom)}</td>
				</tr>`,
					)
					.join("");
				const details = message.items
					.map(
						(row) => `<details class="mb-3">
					<summary>${__("Row")} ${escape(row.row)} · ${escape(row.item_code || row.template)} · ${escape(row.occurrence_count)} ${row.occurrence_count === 1 ? __("date") : __("dates")}</summary>
					<table class="table table-bordered mt-2"><thead><tr><th>${__("Schedule Date")}</th><th>${__("Qty / Date")}</th><th>${__("UOM")}</th></tr></thead>
					<tbody>${row.dates.map((date) => `<tr><td>${escape(date)}</td><td>${escape(row.qty_per_occurrence)}</td><td>${escape(row.uom)}</td></tr>`).join("")}</tbody></table>
				</details>`,
					)
					.join("");
				const preview = new frappe.ui.Dialog({
					title: __("Production Schedule Preview"),
					size: "extra-large",
				});
				preview.$body
					.html(`<p>${__("Production Dates")}: ${escape(message.dates.length)} · ${__("Dated Item Assignments")}: ${escape(message.assignment_count)}</p>
					<p>${__("Responsibilities")}: ${message.responsibilities.map((role) => `${escape(role.supervisor)} · ${escape(role.work_area)}`).join(", ") || __("Template defaults")}</p>
					<div class="table-responsive"><table class="table table-bordered"><thead><tr>
					${["Row", "Item", "From Date", "To Date", "Frequency", "Dates", "Qty / Date", "Total Planned"].map((label) => `<th>${__(label)}</th>`).join("")}
					</tr></thead><tbody>${rows}</tbody></table></div>${details}`);
				preview.show();
			});
		}
		if (frm.doc.docstatus === 1) {
			if (frappe.user.has_role(["SRV Production Planner", "System Manager"])) {
				frm.add_custom_button(__("Update Plan"), () => srv_production_edit_plan(frm));
			}
			frm.add_custom_button(
				__("Dated Plans"),
				() => {
					frappe.route_options = { schedule: frm.doc.name };
					frappe.set_route("List", "SRV Production Assignment");
				},
				__("View"),
			);
			frm.add_custom_button(
				__("Assignments Calendar"),
				() => {
					frappe.route_options = { schedule: frm.doc.name };
					frappe.set_route("List", "SRV Production Assignment", "Calendar");
				},
				__("View"),
			);
			frm.add_custom_button(
				__("Production Entries"),
				() => {
					frappe.route_options = { schedule: frm.doc.name };
					frappe.set_route("List", "SRV Production Entry");
				},
				__("View"),
			);
			if (frm.doc.status !== "Completed") {
				frm.add_custom_button(
					__("Production Entry"),
					async () => {
						const { message } = await frappe.call({
							method: "srv_erp.production.service.get_pending_options",
							args: { schedule: frm.doc.name },
						});
						const areas = (user) =>
							message.responsibilities
								.filter((role) => role.supervisor === user)
								.map((role) => role.work_area);
						let dialog;
						dialog = frappe.prompt(
							[
								{
									fieldname: "supervisor",
									label: __("Supervisor"),
									fieldtype: "Select",
									options: message.supervisors,
									default: message.supervisors[0],
									onchange() {
										if (!dialog) return;
										const options = areas(dialog.get_value("supervisor"));
										return dialog.set_value("work_area", options[0]);
									},
									reqd: 1,
								},
								{
									fieldname: "work_area",
									label: __("Work Area / Operation"),
									fieldtype: "Link",
									options: "Operation",
									get_query() {
										return {
											filters: {
												name: [
													"in",
													areas(
														dialog?.get_value("supervisor") ||
															message.supervisors[0],
													),
												],
											},
										};
									},
									default: areas(message.supervisors[0])[0],
									reqd: 1,
								},
								{
									fieldname: "planned_date",
									label: __("Schedule Date"),
									fieldtype: "Select",
									options: ["", ...message.dates],
									description: __("Leave blank to include all pending dates."),
								},
							],
							(values) =>
								frappe.model.open_mapped_doc({
									method: "srv_erp.production.service.make_production_entry",
									frm,
									args: values,
								}),
							__("Create Production Entry"),
							__("Create"),
						);
					},
					__("Create"),
				);
				frm.page.set_inner_btn_group_as_primary(__("Create"));
			}
		}
	},
});

frappe.ui.form.on("SRV Production Schedule Item", {
	items_add(frm, cdt, cdn) {
		return frappe.model.set_value(cdt, cdn, srv_production_defaults(frm));
	},
	from_date(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.frequency === "Once")
			return frappe.model.set_value(cdt, cdn, "to_date", row.from_date);
	},
	frequency(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.frequency === "Once")
			return frappe.model.set_value(cdt, cdn, "to_date", row.from_date);
	},
	async item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const code = row.item_code || row.template;
		const { message } = code
			? await frappe.db.get_value("Item", code, "item_name")
			: { message: {} };
		await frappe.model.set_value(cdt, cdn, "item_name", message.item_name || "");
	},
	async template(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		await frappe.model.set_value(cdt, cdn, { item_code: null, supervisor: null, uom: null });
		if (!row.template) return;
		const { message } = await frappe.db.get_value("Item", row.template, [
			"custom_production_supervisor",
			"stock_uom",
			"item_name",
		]);
		await frappe.model.set_value(cdt, cdn, {
			supervisor: message.custom_production_supervisor,
			uom: message.stock_uom,
			item_name: message.item_name,
		});
	},
});

function srv_production_defaults(frm) {
	return {
		from_date: frm.doc.start_date || null,
		to_date: frm.doc.end_date || null,
		frequency: frm.doc.frequency,
		interval: frm.doc.interval,
		recurrence_unit: frm.doc.recurrence_unit,
		weekdays: frm.doc.weekdays || "",
		custom_dates: frm.doc.custom_dates || "",
	};
}

async function srv_production_update_defaults(frm, field) {
	if (frm.doc.docstatus !== 0) return;
	const key = { start_date: "from_date", end_date: "to_date" }[field] || field;
	const defaults = srv_production_defaults(frm);
	const previous = frm._planning_defaults || {};
	const required = ["from_date", "to_date", "frequency", "interval", "recurrence_unit"].includes(
		key,
	);
	for (const row of frm.doc.items || []) {
		if (row[key] == null || (required && row[key] === "") || row[key] === previous[key]) {
			await frappe.model.set_value(row.doctype, row.name, key, defaults[key]);
		}
	}
	frm._planning_defaults = { ...previous, [key]: defaults[key] };
}

async function srv_production_edit_plan(frm) {
	const method = "srv_erp.production.updates.";
	const { message: rows } = await frappe.call({
		method: method + "get_plan",
		args: { schedule: frm.doc.name },
	});
	if (!rows.length) return frappe.msgprint(__("This schedule has no active dated plans."));
	const original = new Map(rows.map((row) => [row.name, { ...row }]));
	const dialog = new frappe.ui.Dialog({
		title: __("Update Submitted Production Plan"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "help",
				options: `<p>${__("Edit dated plans below, or select rows and apply common values. Target Qty is the total required, including produced quantity. Recorded production stays unchanged. Original item ranges remain as the submission record; Dated Plans and the calendar show current work.")}</p>`,
			},
			{ fieldtype: "Section Break", label: __("Apply to Selected Rows") },
			{ fieldtype: "Date", fieldname: "new_date", label: __("New Schedule Date") },
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Link",
				fieldname: "new_supervisor",
				label: __("New Supervisor"),
				options: "User",
				get_query: () => ({ query: "srv_erp.production.service.supervisor_query" }),
			},
			{ fieldtype: "Column Break" },
			{ fieldtype: "Float", fieldname: "new_target", label: __("New Total Target Qty") },
			{
				fieldtype: "Button",
				fieldname: "apply_selected",
				label: __("Apply to Selected Rows"),
				click() {
					const selected = dialog.fields_dict.rows.grid.get_selected_children();
					if (!selected.length)
						return frappe.msgprint(__("Select dated plan rows first."));
					const values = {
						new_date: dialog.get_value("new_date"),
						new_supervisor: dialog.get_value("new_supervisor"),
						new_target: dialog.get_value("new_target"),
					};
					if (!values.new_date && !values.new_supervisor && !values.new_target)
						return frappe.msgprint(
							__("Enter a new date, supervisor or target to apply."),
						);
					for (const row of selected) {
						if (values.new_date) row.planned_date = values.new_date;
						if (values.new_supervisor) row.supervisor = values.new_supervisor;
						if (values.new_target) row.target_qty = values.new_target;
						row.remaining_qty = flt(row.target_qty - row.completed_qty, 6);
					}
					dialog.fields_dict.rows.grid.refresh();
				},
			},
			{ fieldtype: "Section Break", label: __("Current Dated Plans") },
			{
				fieldname: "rows",
				fieldtype: "Table",
				label: __("Dated Plans"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: false,
				data: rows,
				fields: [
					{
						fieldname: "item",
						fieldtype: "Data",
						label: __("Item"),
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "item_name",
						fieldtype: "Data",
						label: __("Item Name"),
						read_only: 1,
					},
					{
						fieldname: "work_area",
						fieldtype: "Link",
						options: "Operation",
						label: __("Operation"),
						read_only: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldname: "planned_date",
						fieldtype: "Date",
						label: __("Date"),
						reqd: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "supervisor",
						fieldtype: "Link",
						options: "User",
						label: __("Supervisor"),
						reqd: 1,
						in_list_view: 1,
						columns: 2,
						get_query: () => ({
							query: "srv_erp.production.service.supervisor_query",
						}),
					},
					{
						fieldname: "target_qty",
						onchange() {
							this.doc.remaining_qty = flt(
								this.doc.target_qty - this.doc.completed_qty,
								6,
							);
							this.grid_row.refresh_field("remaining_qty");
						},
						fieldtype: "Float",
						label: __("Target"),
						reqd: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldname: "completed_qty",
						fieldtype: "Float",
						label: __("Produced"),
						read_only: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldname: "remaining_qty",
						fieldtype: "Float",
						label: __("Remaining"),
						read_only: 1,
						in_list_view: 1,
						columns: 1,
					},
					{ fieldname: "status", fieldtype: "Data", label: __("Status"), read_only: 1 },
					{ fieldname: "uom", fieldtype: "Data", label: __("UOM"), read_only: 1 },
				],
			},
			{ fieldtype: "Section Break", label: __("Change Record") },
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason for Update"),
				reqd: 1,
			},
		],
		primary_action_label: __("Save Plan Updates"),
		async primary_action(values) {
			const changed = values.rows
				.filter((row) => {
					const before = original.get(row.name);
					return (
						row.planned_date !== before.planned_date ||
						row.supervisor !== before.supervisor ||
						Number(row.target_qty) !== Number(before.target_qty)
					);
				})
				.map((row) => ({
					name: row.name,
					modified: original.get(row.name).modified,
					row_number: original.get(row.name).row_number,
					completed_qty: original.get(row.name).completed_qty,
					planned_date: row.planned_date,
					supervisor: row.supervisor,
					target_qty: row.target_qty,
				}));
			if (!changed.length)
				return frappe.msgprint(__("Change a date, supervisor or target first."));
			const { message } = await frappe.call({
				method: method + "update_plan",
				args: { schedule: frm.doc.name, rows: changed, reason: values.reason },
				freeze: true,
				freeze_message: __("Updating production plan…"),
				btn: dialog.get_primary_btn(),
			});
			dialog.hide();
			await frm.reload_doc();
			frappe.show_alert({
				message: __("Updated {0} dated plans", [message.updated]),
				indicator: "green",
			});
		},
	});
	for (const row of rows) {
		row.item = row.item_code || row.template;
		row.idx = row.row_number;
	}
	// Frappe hides dialog grid indices globally; keep these visible for row diagnostics.
	dialog.$wrapper.find(".row-index").css("display", "flex");
	dialog.show();
}
