// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Items Ordered in Date Range"] = {
	onload: async function(report) {
		await set_finished_warehouse(report);
	},
	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Sub-total", "Item Summary", "Detailed"],
			default: "Sub-total",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "range",
			label: __("Range"),
			fieldtype: "Select",
			options: ["Daily", "Weekly", "Monthly", "Quarterly", "Yearly"],
			default: "Monthly",
			on_change() {
				const range = frappe.query_report.get_filter_value("range");
				const today = frappe.datetime.get_today();
				const offsets = { Daily: 0, Weekly: -7, Monthly: -1, Quarterly: -3, Yearly: -12 };
				const from_date = range === "Weekly"
					? frappe.datetime.add_days(today, offsets[range])
					: frappe.datetime.add_months(today, offsets[range]);
				frappe.query_report.set_filter_value("from_date", from_date);
				frappe.query_report.set_filter_value("to_date", today);
			},
		},
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "customer_group", label: __("Customer Group"), fieldtype: "Link", options: "Customer Group" },
		{ fieldname: "territory", label: __("Territory"), fieldtype: "Link", options: "Territory" },
		{ fieldname: "sales_person", label: __("Sales Person"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "Brand" },
		{ fieldname: "include_uom", label: __("Include UOM"), fieldtype: "Link", options: "UOM" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: async function() {
				await set_finished_warehouse(frappe.query_report, true);
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			reqd: 1,
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
	],
};

async function set_finished_warehouse(report, replace_existing = false) {
	const warehouse_filter = report.get_filter("warehouse");
	if (!warehouse_filter || (!replace_existing && warehouse_filter.get_value())) {
		return;
	}

	const company = report.get_filter_value("company");
	if (!company) {
		return;
	}

	const warehouses = await frappe.db.get_list("Warehouse", {
		filters: {
			company,
			warehouse_name: "Finished Goods",
			is_group: 0,
			disabled: 0,
		},
		fields: ["name", "warehouse_name"],
		limit: 1,
	});
	const warehouse = warehouses[0];
	await warehouse_filter.set_value(warehouse ? warehouse.name : "");
}
