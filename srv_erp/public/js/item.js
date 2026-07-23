frappe.provide("erpnext.item");
frappe.provide("srv_erp.item");

srv_erp.item.toggle_variant_item_group = function (frm) {
	const is_variant = Boolean(frm.doc.variant_of);
	frm.set_df_property("item_group", "read_only", is_variant ? 1 : 0);
};

frappe.ui.form.on("Item", {
	setup: srv_erp.item.toggle_variant_item_group,
	refresh: srv_erp.item.toggle_variant_item_group,
	variant_of: srv_erp.item.toggle_variant_item_group,
});
