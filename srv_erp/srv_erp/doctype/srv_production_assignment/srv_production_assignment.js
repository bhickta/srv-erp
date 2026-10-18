frappe.ui.form.on("SRV Production Assignment", {
	refresh(frm) {
		if (
			!frm.is_new() &&
			frm.doc.status !== "Cancelled" &&
			frm.doc.remaining_qty > 0 &&
			frappe.model.can_create("SRV Production Entry")
		) {
			frm.add_custom_button(__("Record Production"), () => {
				frappe.model.open_mapped_doc({
					method: "srv_erp.production.service.make_production_entry",
					source_name: frm.doc.schedule,
					args: { supervisor: frm.doc.supervisor, planned_date: frm.doc.planned_date },
				});
			}).addClass("btn-primary");
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Production Entries"), () => {
				frappe.route_options = { schedule: frm.doc.schedule };
				frappe.set_route("List", "SRV Production Entry");
			});
		}
	},
});
