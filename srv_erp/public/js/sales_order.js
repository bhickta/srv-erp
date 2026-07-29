const sales_order_attribute_fields = ["branding_type", "color", "marketed_by"];
const sales_order_discount_refresh_fields = [
	"discount_amount",
	"rate",
	"amount",
	"net_rate",
	"net_amount",
	"base_rate",
	"base_amount",
];

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

function validate_discount_percentage(cdt, cdn) {
	const row = locals[cdt][cdn];
	const discount_percentage = flt(row.discount_percentage);

	if (discount_percentage < 0 || discount_percentage > 100) {
		frappe.model.set_value(cdt, cdn, "discount_percentage", 0);
		frappe.throw(__("Discount (%) must be between 0 and 100."));
	}
}

function refresh_discount_calculated_fields(frm, cdt, cdn) {
	setTimeout(() => {
		sales_order_discount_refresh_fields.forEach((fieldname) => {
			refresh_field(fieldname, cdn, "items");
		});
		frm.refresh_fields([
			"total",
			"net_total",
			"base_total",
			"base_net_total",
			"grand_total",
			"rounded_total",
		]);
	}, 0);
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

	price_list_rate: refresh_discount_calculated_fields,

	discount_percentage(frm, cdt, cdn) {
		validate_discount_percentage(cdt, cdn);
		refresh_discount_calculated_fields(frm, cdt, cdn);
	},

	discount_amount: refresh_discount_calculated_fields,

	rate: refresh_discount_calculated_fields,

	qty: refresh_discount_calculated_fields,
});
