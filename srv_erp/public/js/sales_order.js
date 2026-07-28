const sales_order_attribute_fields = ["branding_type", "color", "marketed_by"];

function copy_parent_value_to_items(frm, fieldname) {
	if (!frm.doc[fieldname]) {
		return;
	}

	(frm.doc.items || []).forEach((row) => {
		frappe.model.set_value(row.doctype, row.name, fieldname, frm.doc[fieldname]);
	});
}

function set_item_attribute_defaults(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	sales_order_attribute_fields.forEach((fieldname) => {
		if (frm.doc[fieldname]) {
			frappe.model.set_value(cdt, cdn, fieldname, frm.doc[fieldname]);
		} else {
			frm.script_manager.copy_from_first_row("items", row, [fieldname]);
		}
	});
}

function copy_item_value_to_all_rows(frm, cdt, cdn, fieldname) {
	if (!frm.doc[fieldname]) {
		erpnext.utils.copy_value_in_all_rows(frm.doc, cdt, cdn, "items", fieldname);
	}
}

frappe.ui.form.on("Sales Order", {
	branding_type(frm) {
		copy_parent_value_to_items(frm, "branding_type");
	},

	color(frm) {
		copy_parent_value_to_items(frm, "color");
	},

	marketed_by(frm) {
		copy_parent_value_to_items(frm, "marketed_by");
	},
});

frappe.ui.form.on("Sales Order Item", {
	item_code(frm, cdt, cdn) {
		set_item_attribute_defaults(frm, cdt, cdn);
	},

	branding_type(frm, cdt, cdn) {
		copy_item_value_to_all_rows(frm, cdt, cdn, "branding_type");
	},

	color(frm, cdt, cdn) {
		copy_item_value_to_all_rows(frm, cdt, cdn, "color");
	},

	marketed_by(frm, cdt, cdn) {
		copy_item_value_to_all_rows(frm, cdt, cdn, "marketed_by");
	},
});
