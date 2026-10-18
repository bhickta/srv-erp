frappe.ui.form.on("SRV Production Entry", {
	setup(frm) {
		frm.set_query("item_code", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: row.planned_item
					? { name: row.planned_item, disabled: 0 }
					: {
							variant_of: row.template || "__select_assignment_first__",
							has_variants: 0,
							disabled: 0,
					  },
			};
		});
		frm.set_query("assignment", "items", () => ({
			filters: {
				schedule: frm.doc.schedule || "",
				status: ["!=", "Cancelled"],
				remaining_qty: [">", 0],
			},
		}));
	},
	refresh(frm) {
		if (frm.doc.schedule && frappe.model.can_read("SRV Production Schedule")) {
			frm.add_custom_button(
				__("Production Schedule"),
				() => frappe.set_route("Form", "SRV Production Schedule", frm.doc.schedule),
				__("View")
			);
		}
		if (frm.is_new() && !frm.doc.items?.length) {
			frm.set_intro(
				__(
					"Open a production schedule and use Create → Production Entry to bring in its pending items."
				),
				"blue"
			);
		}
	},
});
frappe.ui.form.on("SRV Production Entry Item", {
	async assignment(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.assignment) return;
		const { message } = await frappe.call({
			method: "srv_erp.production.service.get_assignment_details",
			args: { assignment: row.assignment },
		});
		if (!frm.doc.schedule) await frm.set_value("schedule", message.schedule);
		await frappe.model.set_value(cdt, cdn, {
			template: message.template,
			planned_item: message.item_code,
			item_code: message.item_code,
			supervisor: message.supervisor,
			planned_date: message.planned_date,
			planned_qty: message.target_qty,
			previously_produced_qty: message.completed_qty,
			remaining_qty: message.remaining_qty,
			qty: message.remaining_qty,
			uom: message.uom,
		});
	},
});
