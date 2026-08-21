import json

import frappe
from frappe import _
from frappe.utils import format_date


MAX_ORDERS_PER_PRINT = 200


@frappe.whitelist()
def get_order_slip_ledger_html(names: list[str] | str) -> str:
	names = parse_order_names(names)
	if not names:
		frappe.throw(_("Select at least one Sales Order to print."))
	if len(names) > MAX_ORDERS_PER_PRINT:
		frappe.throw(
			_("You can print up to {0} Sales Orders at a time.").format(MAX_ORDERS_PER_PRINT)
		)

	orders = []
	for name in names:
		doc = frappe.get_doc("Sales Order", name)
		doc.check_permission("print")
		orders.append(doc)

	dates = sorted(order.transaction_date for order in orders if order.transaction_date)
	date_heading = get_date_heading(dates)
	grand_total = sum(order.grand_total or 0 for order in orders)
	currency = orders[0].currency if len({order.currency for order in orders}) == 1 else None

	return frappe.render_template(
		"srv_erp/templates/order_slip_ledger.html",
		{
			"orders": orders,
			"date_heading": date_heading,
			"grand_total": grand_total,
			"currency": currency,
		},
	)


def parse_order_names(names: list[str] | str) -> list[str]:
	if isinstance(names, str):
		try:
			names = json.loads(names)
		except (TypeError, ValueError):
			names = [names]

	if not isinstance(names, list):
		return []

	return list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))


def get_date_heading(dates) -> str:
	if not dates:
		return ""
	if dates[0] == dates[-1]:
		return format_date(dates[0])
	return _("{0} to {1}").format(format_date(dates[0]), format_date(dates[-1]))
