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
					<summary>${__("Row")} ${escape(row.row)} · ${escape(row.item_code || row.template)} · ${escape(row.occurrence_count)} ${__("dates")}</summary>
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
	for (const row of frm.doc.items || []) {
		if (!row[key] || row[key] === previous[key]) {
			await frappe.model.set_value(row.doctype, row.name, key, defaults[key]);
		}
	}
	frm._planning_defaults = { ...previous, [key]: defaults[key] };
}
