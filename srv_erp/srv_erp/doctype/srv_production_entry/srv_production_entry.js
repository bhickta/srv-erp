frappe.ui.form.on("SRV Production Entry", {
	setup(frm) {
		frm.set_query("item_code", () => ({
			filters: { variant_of: frm.doc.template || "", has_variants: 0, disabled: 0 },
		}));
		frm.set_query("assignment", () => ({
			filters: { status: ["not in", ["Cancelled", "Completed"]] },
		}));
	},
	async assignment(frm) {
		if (!frm.doc.assignment) return;
		const { message } = await frappe.call({
			method: "srv_erp.production.service.get_assignment_details",
			args: { assignment: frm.doc.assignment },
		});
		await frm.set_value({
			company: message.company,
			template: message.template,
			supervisor: message.supervisor,
			uom: message.uom,
			item_code: null,
		});
	},
});
