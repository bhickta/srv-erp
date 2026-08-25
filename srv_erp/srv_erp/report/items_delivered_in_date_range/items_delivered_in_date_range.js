// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Items Delivered in Date Range"] = {
	onload: async function(report) {
		await set_finished_warehouse(report);
	},
	filters: [
		{
			fieldname: "pending_only",
			label: __("Pending Only"),
			fieldtype: "Check",
			default: 1,
			description: __("Show only delivered items whose Sales Order quantity is still pending."),
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
			default: "Daily",
			reqd: 1,
			on_change: function() {
				let range = frappe.query_report.get_filter_value('range');
				let today = frappe.datetime.get_today();
				let from_date = today;
				
				if (range === 'Weekly') {
					from_date = frappe.datetime.add_days(today, -7);
				} else if (range === 'Monthly') {
					from_date = frappe.datetime.add_months(today, -1);
				} else if (range === 'Quarterly') {
					from_date = frappe.datetime.add_months(today, -3);
				} else if (range === 'Yearly') {
					from_date = frappe.datetime.add_months(today, -12);
				}
				
				frappe.query_report.set_filter_value('from_date', from_date);
				frappe.query_report.set_filter_value('to_date', today);
			}
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
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
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "include_uom",
			label: __("Include UOM"),
			fieldtype: "Link",
			options: "UOM",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
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
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}

		const status_fields = [
			"stock_ordered_qty",
			"stock_delivered_qty",
			"stock_available_qty",
			"stock_shortfall_qty",
		];
		const shortage = flt(data.stock_shortfall_qty);
		const ordered = flt(data.stock_ordered_qty);
		const delivered = flt(data.stock_delivered_qty);
		const stock = flt(data.stock_available_qty);

		if (column.fieldname === "item_name") {
			const color = shortage > 0 ? "#b3261e" : "#137333";
			return `<span style="border-left:3px solid ${color};padding-left:6px">${value}</span>`;
		}
		if (!status_fields.includes(column.fieldname)) {
			return value;
		}

		let foreground = "#1a73e8";
		let background = "#e8f0fe";
		if (column.fieldname === "stock_shortfall_qty") {
			foreground = shortage > 0 ? "#b3261e" : "#137333";
			background = shortage > 0 ? "#fce8e6" : "#e6f4ea";
		} else if (column.fieldname === "stock_available_qty") {
			const stock_is_sufficient = stock >= Math.max(ordered - delivered, 0);
			foreground = stock_is_sufficient ? "#137333" : "#b3261e";
			background = stock_is_sufficient ? "#e6f4ea" : "#fce8e6";
		} else if (column.fieldname === "stock_delivered_qty") {
			foreground = delivered > 0 ? "#137333" : "#b3261e";
			background = delivered > 0 ? "#e6f4ea" : "#fce8e6";
		}

		return `<span style="display:block;margin:-2px -4px;padding:2px 4px;border-radius:3px;color:${foreground};background:${background};font-weight:700">${value}</span>`;
	},
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
