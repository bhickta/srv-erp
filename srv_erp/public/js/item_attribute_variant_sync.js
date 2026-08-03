frappe.provide("srv_erp.item_attribute_variant_sync");

srv_erp.item_attribute_variant_sync = {
	after_save(frm) {
		if (frm.doc.numeric_values) {
			return;
		}

		frappe.call({
			method: "srv_erp.variant_auto_creation.sync_item_attribute_and_get_status",
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

	add_brand_sync_button(frm) {
		frm.add_custom_button(__("Sync Brand Variants"), () => {
			srv_erp.item_attribute_variant_sync.sync_all_brands();
		});
	},

	sync_all_brands() {
		frappe.call({
			method: "srv_erp.variant_auto_creation.sync_brand_masters_and_get_status",
			freeze: true,
			freeze_message: __("Syncing brands..."),
			callback: (r) => {
				srv_erp.item_attribute_variant_sync.handle_status(r.message || {});
			},
		});
	},

	handle_status(status) {
		if (!status.applicable || !status.missing_count) {
			if (status.attribute_value_created) {
				frappe.show_alert({
					message: __("Synced {0} brand values.", [status.attribute_value_created]),
					indicator: "green",
				});
			}

			if (status.auto_create_enabled) {
				srv_erp.item_attribute_variant_sync.show_result(status);
			}
			return;
		}

		if (status.auto_create_enabled) {
			srv_erp.item_attribute_variant_sync.show_result(status);
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
				srv_erp.item_attribute_variant_sync.show_result(r.message || {});
			},
		});
	},

	show_result(result) {
		const created = result.created || 0;
		const queued = result.queued || 0;
		const skipped = result.skipped || 0;
		const errors = result.errors || 0;

		frappe.show_alert({
			message: __("Created {0}, queued {1}, skipped {2}.", [created, queued, skipped]),
			indicator: errors ? "orange" : "green",
		});
	},
};

frappe.ui.form.on("Item Attribute", {
	after_save(frm) {
		srv_erp.item_attribute_variant_sync.after_save(frm);
	},
});

frappe.ui.form.on("Brand", {
	refresh(frm) {
		srv_erp.item_attribute_variant_sync.add_brand_sync_button(frm);
	},

	after_save(frm) {
		srv_erp.item_attribute_variant_sync.after_brand_save(frm);
	},
});

frappe.listview_settings["Brand"] = {
	onload(listview) {
		listview.page.add_actions_menu_item(__("Sync Brand Variants"), () => {
			srv_erp.item_attribute_variant_sync.sync_all_brands();
		});
	},
};
