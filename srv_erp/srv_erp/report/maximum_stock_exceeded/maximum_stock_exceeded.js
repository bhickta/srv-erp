frappe.query_reports["Maximum Stock Exceeded"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "item_code",
			label: __("Items"),
			fieldtype: "MultiSelectList",
			options: "Item",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouses"),
			fieldtype: "MultiSelectList",
			options: "Warehouse",
		},
		{
			fieldname: "include_disabled_items",
			label: __("Include Disabled Items"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "only_exceeded",
			label: __("Only Items Over Maximum"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "excess_qty" && data && data.excess_qty > 0) {
			value = "<span style='color:red;font-weight:bold'>" + value + "</span>";
		}

		return value;
	},
};
