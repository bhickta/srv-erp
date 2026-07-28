// Copyright (c) 2026, Nishant Bhickta and contributors

frappe.query_reports["DSR Expense Summary"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
		{
			fieldname: "audit_status",
			label: __("Audit Status"),
			fieldtype: "Select",
			options: "\nPending\nPaid\nRejected\nPartially Paid",
		},
	],
};
