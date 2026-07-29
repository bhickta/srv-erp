const sales_order_attribute_fields = ["branding_type", "color", "marketed_by"];
const sales_order_rate_discount_field = "srv_discount_percentage";
const sales_order_base_rate_field = "srv_rate_before_discount";
const sales_order_last_discount_field = "srv_last_discount_percentage";
const sales_order_discount_refresh_fields = [
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
	const discount_percentage = flt(row[sales_order_rate_discount_field]);

	if (discount_percentage < 0 || discount_percentage > 100) {
		frappe.model.set_value(cdt, cdn, sales_order_rate_discount_field, 0);
		frappe.throw(__("Discount (%) on Rate must be between 0 and 100."));
	}
}

function get_previous_discounted_rate(row) {
	const base_rate = flt(row[sales_order_base_rate_field]);
	const discount_percentage = flt(row[sales_order_last_discount_field]);

	if (!base_rate || !discount_percentage) {
		return null;
	}

	return flt(base_rate * (1 - discount_percentage / 100), precision("rate", row));
}

function is_previous_discounted_rate(row) {
	const previous_discounted_rate = get_previous_discounted_rate(row);

	if (previous_discounted_rate === null) {
		return false;
	}

	return Math.abs(flt(row.rate) - previous_discounted_rate) <= 0.000001;
}

function calculate_discounted_rate(row, base_rate) {
	return flt(
		base_rate * (1 - flt(row[sales_order_rate_discount_field]) / 100),
		precision("rate", row)
	);
}

function apply_rate_discount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const discount_percentage = flt(row[sales_order_rate_discount_field]);
	let base_rate = flt(row[sales_order_base_rate_field]);

	if (row.__applying_srv_rate_discount) {
		return;
	}

	if (discount_percentage) {
		if (!base_rate || !is_previous_discounted_rate(row)) {
			base_rate = flt(row.rate);
		}

		row.__applying_srv_rate_discount = true;
		frappe.model
			.set_value(cdt, cdn, {
				[sales_order_base_rate_field]: base_rate,
				rate: calculate_discounted_rate(row, base_rate),
				[sales_order_last_discount_field]: discount_percentage,
			})
			.then(() => {
				row.__applying_srv_rate_discount = false;
				refresh_discount_calculated_fields(frm, cdt, cdn);
			});
		return;
	}

	if (base_rate && is_previous_discounted_rate(row)) {
		row.__applying_srv_rate_discount = true;
		frappe.model
			.set_value(cdt, cdn, {
				rate: base_rate,
				[sales_order_base_rate_field]: 0,
				[sales_order_last_discount_field]: 0,
			})
			.then(() => {
				row.__applying_srv_rate_discount = false;
				refresh_discount_calculated_fields(frm, cdt, cdn);
			});
		return;
	}

	frappe.model.set_value(cdt, cdn, {
		[sales_order_base_rate_field]: 0,
		[sales_order_last_discount_field]: 0,
	});
	refresh_discount_calculated_fields(frm, cdt, cdn);
}

function schedule_rate_discount(frm, cdt, cdn) {
	setTimeout(() => apply_rate_discount(frm, cdt, cdn), 0);
}

function refresh_discount_calculated_fields(frm, cdt, cdn) {
	setTimeout(() => {
		if (frm.cscript && frm.cscript.calculate_taxes_and_totals) {
			frm.cscript.calculate_taxes_and_totals();
		}

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

	price_list_rate: schedule_rate_discount,

	srv_discount_percentage(frm, cdt, cdn) {
		validate_discount_percentage(cdt, cdn);
		apply_rate_discount(frm, cdt, cdn);
	},

	discount_percentage: schedule_rate_discount,

	discount_amount: schedule_rate_discount,

	rate(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.__applying_srv_rate_discount) {
			schedule_rate_discount(frm, cdt, cdn);
		}
	},

	qty: refresh_discount_calculated_fields,
});
