/* global srv_erp */

frappe.provide("srv_erp.list_view");

srv_erp.list_view.setup_tree_group_filters = function (listview, configs) {
	configs.forEach((config) => {
		const field = listview.page.fields_dict[config.fieldname];
		if (!field) {
			return;
		}

		// Standard Link filters default to equality unless Frappe happens to list
		// the target DocType in boot.treeviews. Set the hierarchy operator
		// explicitly so selecting a parent group also matches every descendant.
		field.df.condition = config.condition || "descendants of (inclusive)";
		field.get_query = () => ({
			filters: config.link_filters || { is_group: 1 },
		});
	});
};
