frappe.provide("erpnext.item");
frappe.provide("srv_erp.item");

srv_erp.item.toggle_variant_item_group = function (frm) {
	const is_variant = Boolean(frm.doc.variant_of);
	frm.set_df_property("item_group", "read_only", is_variant ? 1 : 0);
};

frappe.ui.form.on("Item", {
	setup: srv_erp.item.toggle_variant_item_group,
	refresh(frm) {
		srv_erp.item.toggle_variant_item_group(frm);
		if (!frm.is_new() && frm.doc.has_variants) {
			frm.add_custom_button(__("Manage Variant Prices"), () => {
				frappe.route_options = { item_code: frm.doc.name };
				frappe.set_route("List", "Item Price");
			}, __("Prices"));
		}
	},
	variant_of: srv_erp.item.toggle_variant_item_group,
});
