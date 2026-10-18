frappe.ui.form.on("SRV Production Schedule", {
	setup(frm) {
		frm.set_query("template", "items", () => ({ filters: { has_variants: 1, disabled: 0 } }));
		frm.set_query("item_code", "items", (doc, cdt, cdn) => ({
			filters: {
				variant_of: locals[cdt][cdn].template || "__select_template_first__",
				has_variants: 0,
				disabled: 0,
			},
		}));
	},
	refresh(frm) {
		frm.set_df_property("items", "read_only", frm.doc.docstatus !== 0);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview Dates"), async () => {
				const { message } = await frm.call("preview");
				const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
				const rows = message.items
					.map(
						(row) =>
							`<tr><td>${escape(row.item_code || row.template)}</td><td>${escape(
								row.supervisor
							)}</td><td>${escape(row.qty_per_occurrence)}</td><td>${escape(
								row.planned_qty
							)} ${escape(row.uom)}</td></tr>`
					)
					.join("");
				frappe.msgprint({
					title: __("Production Schedule Preview"),
					wide: true,
					message: `<p>${__("Production Dates")}: ${message.dates
						.map(escape)
						.join(", ")}</p>
					<p>${__("Dated Item Assignments")}: ${message.assignment_count}</p>
					<table class="table table-bordered"><thead><tr><th>${__("Item")}</th><th>${__(
						"Supervisor"
					)}</th><th>${__("Qty / Date")}</th><th>${__(
						"Total Planned"
					)}</th></tr></thead><tbody>${rows}</tbody></table>`,
				});
			});
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Assignments Calendar"),
				() => {
					frappe.route_options = { schedule: frm.doc.name };
					frappe.set_route("List", "SRV Production Assignment", "Calendar");
				},
				__("View")
			);
			frm.add_custom_button(
				__("Production Entries"),
				() => {
					frappe.route_options = { schedule: frm.doc.name };
					frappe.set_route("List", "SRV Production Entry");
				},
				__("View")
			);
			if (frm.doc.status !== "Completed") {
				frm.add_custom_button(
					__("Production Entry"),
					async () => {
						const { message } = await frappe.call({
							method: "srv_erp.production.service.get_pending_options",
							args: { schedule: frm.doc.name },
						});
						frappe.prompt(
							[
								{
									fieldname: "supervisor",
									label: __("Supervisor"),
									fieldtype: "Select",
									options: message.supervisors,
									default: message.supervisors[0],
									reqd: 1,
								},
								{
									fieldname: "planned_date",
									label: __("Planned Date"),
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
							__("Create")
						);
					},
					__("Create")
				);
				frm.page.set_inner_btn_group_as_primary(__("Create"));
			}
		}
	},
});

frappe.ui.form.on("SRV Production Schedule Item", {
	async template(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		await frappe.model.set_value(cdt, cdn, { item_code: null, supervisor: null, uom: null });
		if (!row.template) return;
		const { message } = await frappe.db.get_value("Item", row.template, [
			"custom_production_supervisor",
			"stock_uom",
		]);
		await frappe.model.set_value(cdt, cdn, {
			supervisor: message.custom_production_supervisor,
			uom: message.stock_uom,
		});
	},
});
