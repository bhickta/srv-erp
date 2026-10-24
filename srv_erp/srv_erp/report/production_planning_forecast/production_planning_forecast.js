// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Production Planning Forecast"] = {
	filters: [
		{
			fieldname: "show_sales_by",
			label: __("Show Sales By"),
			fieldtype: "Select",
			options: ["Brand (Variant)", "Base Item (All Brands)"],
			default: "Brand (Variant)",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "Brand" },
		{
			fieldname: "include_uom",
			label: __("Include UOM"),
			fieldtype: "Link",
			options: "UOM",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query() {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						is_group: 0,
						disabled: 0,
					},
				};
			},
		},
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
	],
};
