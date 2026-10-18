frappe.ui.form.on("SRV Production Assignment", {
	refresh(frm) {
		if (
			!frm.is_new() &&
			frm.doc.status !== "Cancelled" &&
			frm.doc.remaining_qty > 0 &&
			frappe.model.can_create("SRV Production Entry")
		) {
			frm.add_custom_button(__("Record Production"), () => {
				frappe.new_doc("SRV Production Entry", {
					assignment: frm.doc.name,
					company: frm.doc.company,
					template: frm.doc.template,
					supervisor: frm.doc.supervisor,
					uom: frm.doc.uom,
				});
			}).addClass("btn-primary");
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Production Entries"), () => {
				frappe.route_options = { assignment: frm.doc.name };
				frappe.set_route("List", "SRV Production Entry");
			});
		}
	},
});
