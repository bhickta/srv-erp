// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Inward Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
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
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "Select",
			options: "\nPurchase Receipt\nStock Entry",
			on_change() {
				frappe.query_report.set_filter_value("voucher_no", "");
			},
		},
		{
			fieldname: "voucher_no",
			label: __("Voucher"),
			fieldtype: "Dynamic Link",
			options: "voucher_type",
			get_query() {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						docstatus: 1,
					},
				};
			},
		},
		{
			fieldname: "stock_entry_type",
			label: __("Stock Entry Type"),
			fieldtype: "Link",
			options: "Stock Entry Type",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "supplier_group",
			label: __("Supplier Group"),
			fieldtype: "Link",
			options: "Supplier Group",
		},
		{
			fieldname: "supplier_delivery_note",
			label: __("Supplier Delivery Note"),
			fieldtype: "Data",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query() {
				return {
					query: "erpnext.controllers.queries.item_query",
					filters: { is_stock_item: 1 },
				};
			},
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
			fieldname: "warehouse",
			label: __("Target Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query() {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						disabled: 0,
					},
				};
			},
		},
		{
			fieldname: "source_warehouse",
			label: __("Source Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query() {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						disabled: 0,
					},
				};
			},
		},
		{
			fieldname: "purchase_order",
			label: __("Purchase Order"),
			fieldtype: "Link",
			options: "Purchase Order",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "batch_no",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			default: "Item",
			options:
				"\nVoucher\nVoucher Type\nSupplier\nSupplier Group\nItem\nItem Group\nWarehouse\nPosting Date\nStock Entry Type",
		},
		{
			fieldname: "sort_by",
			label: __("Sort By"),
			fieldtype: "Select",
			options:
				"Posting Date\nVoucher\nSupplier\nItem\nItem Group\nWarehouse\nQuantity\nStock Value",
			default: "Posting Date",
		},
		{
			fieldname: "sort_order",
			label: __("Sort Order"),
			fieldtype: "Select",
			options: "Descending\nAscending",
			default: "Descending",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}

		if (data.is_group) {
			return `<strong>${value || ""}</strong>`;
		}
		if (column.fieldname === "in_qty" && flt(data.in_qty) > 0) {
			return `<span style="color:#137333;font-weight:600">${value}</span>`;
		}
		return value;
	},
};
