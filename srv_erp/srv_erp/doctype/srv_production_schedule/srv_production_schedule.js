frappe.ui.form.on("SRV Production Schedule", {
	setup(frm) {
		frm.set_query("template", () => ({ filters: { has_variants: 1, disabled: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview Dates"), async () => {
				const { message } = await frm.call("preview");
				const escape = frappe.utils.escape_html;
				const rows = message.dates
					.map((date) => `<tr><td>${escape(date)}</td></tr>`)
					.join("");
				frappe.msgprint({
					title: __("Production Schedule Preview"),
					message: `<p>${escape(__("Supervisor"))}: ${escape(message.supervisor)}</p>
						<p>${escape(__("Occurrences"))}: ${message.dates.length} · ${escape(__("Total Quantity"))}: ${
						message.total_qty
					} ${escape(message.uom)}</p>
						<table class="table table-bordered"><thead><tr><th>${escape(
							__("Production Date")
						)}</th></tr></thead><tbody>${rows}</tbody></table>`,
					wide: true,
				});
			});
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Assignments Calendar"), () => {
				frappe.route_options = { schedule: frm.doc.name };
				frappe.set_route("List", "SRV Production Assignment", "Calendar");
			});
		}
	},
	async template(frm) {
		if (!frm.doc.template) return;
		const { message } = await frappe.db.get_value("Item", frm.doc.template, [
			"custom_production_supervisor",
			"stock_uom",
		]);
		await frm.set_value({
			supervisor: message.custom_production_supervisor,
			uom: message.stock_uom,
		});
	},
});
