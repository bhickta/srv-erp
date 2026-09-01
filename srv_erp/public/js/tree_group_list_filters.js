frappe.provide("srv_erp.list_view");

srv_erp.list_view.setup_tree_group_filters = function (listview, configs) {
	configs.forEach((config) => {
		const field = listview.page.fields_dict[config.fieldname];
		if (!field) {
			return;
		}

		field.get_query = () => ({
			filters: config.link_filters || { is_group: 1 },
		});
	});
};
