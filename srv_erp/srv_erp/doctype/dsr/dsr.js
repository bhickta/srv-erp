// Copyright (c) 2026, Nishant Bhickta and contributors
// For license information, please see license.txt

const DSR_AUDIT_ROLES = [
	"Accounts Manager",
	"Auditor",
	"Payment Auditor",
	"System Manager",
];

frappe.ui.form.on("DSR", {
	setup(frm) {
		frm.set_query("type", "daily_sales_expenses_by_admin", () => ({
			filters: { disabled: 0, is_fuel: 0 },
		}));
		frm.set_query("type", "daily_sales_expense_by_admin_approved_amount", () => ({
			filters: { disabled: 0, is_fuel: 0 },
		}));
		frm.set_query("sales_person", "dsr_sales_person_accompanied", () => ({
			filters: { name: ["!=", frm.doc.sales_person || ""] },
		}));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.sales_person && frm.doc.date) {
			set_last_reading(frm);
		}
	},

	refresh(frm) {
		configure_audit_fields(frm);
		show_audit_status(frm);
	},

	date(frm) {
		if (frm.doc.date) {
			const day = frappe.datetime.str_to_obj(frm.doc.date).toLocaleDateString(undefined, {
				weekday: "long",
			});
			frm.set_value("custom_day", day);
		}
		if (frm.is_new() && frm.doc.sales_person) {
			set_last_reading(frm);
		}
	},

	sales_person(frm) {
		if (frm.is_new() && frm.doc.sales_person && frm.doc.date) {
			set_last_reading(frm);
		}
		update_travel_preview(frm);
	},

	start_reading(frm) {
		update_travel_preview(frm);
	},

	end_reading(frm) {
		update_travel_preview(frm);
	},

	rate_per_liter(frm) {
		update_fuel_quantity(frm);
	},

	amount_paid(frm) {
		update_fuel_quantity(frm);
	},

	fuel_added(frm) {
		update_fuel_quantity(frm);
	},

	payment_audited(frm) {
		if (frm.doc.payment_audited) {
			frm.set_value({
				payment_rejected: 0,
				partially_paid: 0,
				reason_for_rejection: "",
			});
		}
	},

	payment_rejected(frm) {
		if (frm.doc.payment_rejected) {
			frm.set_value({
				payment_audited: 0,
				partially_paid: 0,
			});
		} else {
			frm.set_value("reason_for_rejection", "");
		}
	},

	partially_paid(frm) {
		if (!frm.doc.partially_paid) {
			return;
		}

		frm.set_value({
			payment_audited: 0,
			payment_rejected: 0,
			reason_for_rejection: "",
		});

		const approved_field = "daily_sales_expense_by_admin_approved_amount";
		if ((frm.doc[approved_field] || []).length === 0) {
			(frm.doc.daily_sales_expenses_by_admin || []).forEach((expense) => {
				const approved = frm.add_child(approved_field);
				approved.type = expense.type;
				approved.amount = expense.amount;
				approved.description = expense.description;
			});
			frm.refresh_field(approved_field);
		}
	},
});

function set_last_reading(frm) {
	frm.call("set_last_end_reading").then((response) => {
		if (response.message !== undefined) {
			frm.set_value("start_reading", flt(response.message));
			update_travel_preview(frm);
		}
	});
}

function update_travel_preview(frm) {
	const distance = Math.max(flt(frm.doc.end_reading) - flt(frm.doc.start_reading), 0);
	frm.set_value("km_travelled", distance);

	if (!frm.doc.sales_person) {
		frm.set_value("amount_for_travel", 0);
		return;
	}

	frappe.db
		.get_value("Sales Person", frm.doc.sales_person, "travel_rate")
		.then((response) => {
			const rate = flt(response.message?.travel_rate);
			frm.set_value("amount_for_travel", distance * rate);
		});
}

function update_fuel_quantity(frm) {
	const quantity =
		frm.doc.fuel_added && flt(frm.doc.rate_per_liter)
			? flt(frm.doc.amount_paid) / flt(frm.doc.rate_per_liter)
			: 0;
	frm.set_value("fuel_quantity", flt(quantity, 3));
}

function configure_audit_fields(frm) {
	const can_audit = DSR_AUDIT_ROLES.some((role) => frappe.user.has_role(role));
	const audit_fields = [
		"payment_audited",
		"payment_rejected",
		"partially_paid",
		"reason_for_rejection",
		"daily_sales_expense_by_admin_approved_amount",
	];

	audit_fields.forEach((fieldname) => {
		frm.set_df_property(fieldname, "hidden", can_audit ? 0 : 1);
		frm.set_df_property(fieldname, "read_only", can_audit ? 0 : 1);
	});

	const approved_field = frm.fields_dict.daily_sales_expense_by_admin_approved_amount;
	if (approved_field) {
		approved_field.grid.cannot_add_rows = !can_audit;
		approved_field.grid.only_sortable = !can_audit;
		frm.refresh_field("daily_sales_expense_by_admin_approved_amount");
	}
}

function show_audit_status(frm) {
	frm.dashboard.clear_headline();
	if (frm.doc.payment_rejected) {
		frm.dashboard.set_headline(
			__(
				"<span class='text-danger'><b>Payment rejected.</b></span> Reason: {0}",
				[frm.doc.reason_for_rejection || __("No reason provided")],
			),
		);
	} else if (frm.doc.partially_paid) {
		frm.dashboard.set_headline(__("<b>Payment marked as partially paid.</b>"));
	} else if (frm.doc.payment_audited) {
		frm.dashboard.set_headline(__("<span class='text-success'><b>Payment audited.</b></span>"));
	}
}
