// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Items Sold in Date Range"] = {
	filters: [
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
				const from_date =
					range === "Weekly"
						? frappe.datetime.add_days(today, offsets[range])
						: frappe.datetime.add_months(today, offsets[range]);
				frappe.query_report.set_filter_value("from_date", from_date);
				frappe.query_report.set_filter_value("to_date", today);
			},
		},
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
		{ fieldname: "territory", label: __("Territory"), fieldtype: "Link", options: "Territory" },
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "Brand" },
		{ fieldname: "include_uom", label: __("Include UOM"), fieldtype: "Link", options: "UOM" },
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

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "voucher" && data && data.voucher_names) {
			const count = Number(data.voucher_count) || 0;
			const label = count === 1 ? __("1 Voucher") : __("{0} Vouchers", [count]);
			value = `<a href="javascript:void(0)" class="items-sold-voucher-link" data-vouchers="${encodeURIComponent(data.voucher_names)}">${label}</a>`;
		}

		return value;
	},

	onload(report) {
		$(report.page.wrapper)
			.off("click.items_sold_vouchers", ".items-sold-voucher-link")
			.on("click.items_sold_vouchers", ".items-sold-voucher-link", (event) => {
				event.preventDefault();
				const vouchers = decodeURIComponent(
					$(event.currentTarget).attr("data-vouchers") || ""
				)
					.split("||")
					.filter(Boolean);
				show_delivery_notes(vouchers);
			});
	},
};

function show_delivery_notes(vouchers) {
	const links = vouchers
		.map((voucher) => {
			const label = frappe.utils.escape_html(voucher);
			const href = frappe.utils.get_form_link("Delivery Note", voucher);
			return `<li><a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a></li>`;
		})
		.join("");
	const dialog = new frappe.ui.Dialog({
		title: __("Contributing Delivery Notes"),
		fields: [{ fieldname: "delivery_notes", fieldtype: "HTML" }],
		size: "small",
	});
	dialog.fields_dict.delivery_notes.$wrapper.html(`<ul class="mb-0 pl-4">${links}</ul>`);
	dialog.show();
}
