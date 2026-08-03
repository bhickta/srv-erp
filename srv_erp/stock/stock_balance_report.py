import frappe


def use_srv_stock_balance_report():
	if not frappe.db.exists("Report", "Stock Balance"):
		return

	frappe.db.set_value(
		"Report",
		"Stock Balance",
		{
			"module": "Srv Erp",
			"report_type": "Script Report",
			"is_standard": "Yes",
		},
		update_modified=False,
	)
	frappe.clear_cache()
