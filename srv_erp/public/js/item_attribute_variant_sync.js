frappe.provide("srv_erp.item_attribute_variant_sync");

srv_erp.item_attribute_variant_sync = {
	after_save(frm) {
		if (frm.doc.numeric_values) {
			return;
		}

		frappe.call({
			method: "srv_erp.variant_auto_creation.get_item_attribute_variant_sync_status",
			args: {
				attribute: frm.doc.name,
			},
			callback: (r) => {
				srv_erp.item_attribute_variant_sync.handle_status(r.message || {});
			},
		});
	},

	after_brand_save(frm) {
		frappe.call({
			method: "srv_erp.variant_auto_creation.sync_brand_attribute_and_get_status",
			args: {
				brand: frm.doc.brand || frm.doc.name,
			},
			callback: (r) => {
				srv_erp.item_attribute_variant_sync.handle_status(r.message || {});
			},
		});
	},

	handle_status(status) {
		if (!status.applicable || !status.missing_count) {
			return;
		}

		if (status.auto_create_enabled) {
			frappe.show_alert({
				message: __("Variant sync is running for {0}.", [status.attribute]),
				indicator: "blue",
			});
			return;
		}

		const message = status.has_more
			? __(
					"{0}+ missing variants found for {1}. Please narrow from Variant Coverage before creating.",
					[status.max_create_rows, status.attribute]
				)
			: __(
					"{0} missing variants found for {1}. Create them now?",
					[status.missing_count, status.attribute]
				);

		if (status.has_more) {
			frappe.msgprint({
				message,
				indicator: "orange",
				title: __("Variant Sync"),
			});
			return;
		}

		frappe.confirm(message, () => {
			srv_erp.item_attribute_variant_sync.create_missing_variants(status.attribute);
		});
	},

	create_missing_variants(attribute) {
		frappe.call({
			method: "srv_erp.variant_auto_creation.create_missing_variants_for_item_attribute",
			args: {
				attribute,
			},
			freeze: true,
			freeze_message: __("Creating missing variants..."),
			callback: (r) => {
				const result = r.message || {};
				frappe.show_alert({
					message: __(
						"Created {0}, queued {1}, skipped {2}.",
						[result.created || 0, result.queued || 0, result.skipped || 0]
					),
					indicator: result.errors ? "orange" : "green",
				});
			},
		});
	},
};

frappe.ui.form.on("Item Attribute", {
	after_save(frm) {
		srv_erp.item_attribute_variant_sync.after_save(frm);
	},
});

frappe.ui.form.on("Brand", {
	after_save(frm) {
		srv_erp.item_attribute_variant_sync.after_brand_save(frm);
	},
});
