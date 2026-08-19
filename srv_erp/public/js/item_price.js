frappe.ui.form.on("Item Price", {
	setup(frm) {
		// ERPNext normally excludes templates. A template price is the master record
		// from which SRV ERP maintains the concrete prices used by transactions.
		frm.set_query("item_code", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		const is_master = Boolean(frm.doc.is_variant_price_template);
		const is_managed = Boolean(frm.doc.variant_price_template);

		if (is_master) {
			frm.dashboard.set_headline_alert(
				__("Master variant price: saving here updates every variant automatically."),
				"blue"
			);
		}

		if (is_managed) {
			frm.dashboard.set_headline_alert(
				__("Managed by template price {0}.", [frm.doc.variant_price_template]),
				"blue"
			);
			frm.disable_save();
		}
	},
});
