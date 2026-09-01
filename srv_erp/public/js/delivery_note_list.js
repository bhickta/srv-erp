const standard_delivery_note_listview_settings =
	frappe.listview_settings["Delivery Note"] || {};

frappe.listview_settings["Delivery Note"] = {
	...standard_delivery_note_listview_settings,
	onload(listview) {
		standard_delivery_note_listview_settings.onload?.(listview);
		srv_erp.list_view.setup_tree_group_filters(listview, [
			{ fieldname: "customer_group" },
		]);
	},
};
