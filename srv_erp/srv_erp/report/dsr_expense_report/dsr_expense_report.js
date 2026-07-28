// Copyright (c) 2026, Nishant Bhickta and contributors

frappe.query_reports["DSR Expense Report"] = {
	onload(report) {
		add_dsr_date_shortcuts(report);
	},
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
		{
			default: 0,
			fieldname: "group_by_expense_type",
			label: __("Group by Expense Type"),
			fieldtype: "Check",
		},
	],
};

function add_dsr_date_shortcuts(report) {
	report.page.add_inner_button(__("Today"), () => {
		frappe.query_report.get_filter("from_date").set_value(frappe.datetime.get_today());
		frappe.query_report.get_filter("to_date").set_value(frappe.datetime.get_today());
	});
	report.page.add_inner_button(__("This Week"), () => {
		frappe.query_report.get_filter("from_date").set_value(frappe.datetime.week_start());
		frappe.query_report.get_filter("to_date").set_value(frappe.datetime.week_end());
	});
	report.page.add_inner_button(__("This Month"), () => {
		frappe.query_report.get_filter("from_date").set_value(frappe.datetime.month_start());
		frappe.query_report.get_filter("to_date").set_value(frappe.datetime.month_end());
	});
}
