import json

import frappe
from frappe import _
import json
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import flt, format_date

MAX_ORDERS_PER_PRINT = 200


def ensure_print_permission(order: "frappe.Document") -> None:
	for ptype in ("read", "print"):
		if frappe.has_permission(order.doctype, ptype, order):
			return

	order._handle_permission_failure("print")


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
		ensure_print_permission(doc)
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



@frappe.whitelist()
def get_pending_order_slip_ledger_html(names: list[str] | str) -> str:
	names = parse_order_names(names)

	if not names:
		frappe.throw(_("Select at least one Sales Order to print."))

	if len(names) > MAX_ORDERS_PER_PRINT:
		frappe.throw(
			_(
				"You can print up to {0} Sales Orders at a time."
			).format(MAX_ORDERS_PER_PRINT)
		)

	orders = []
	dates = []
	grand_total = 0
	currency = None

	for name in names:
		order = frappe.get_doc("Sales Order", name)

		ensure_print_permission(order)
		pending_items = []

		for item in order.items:
			ordered_qty = flt(item.qty)
			delivered_qty = flt(item.delivered_qty)

			pending_qty = ordered_qty - delivered_qty

			if pending_qty <= 0:
				continue

			pending_item = deepcopy(item)
			pending_item.qty = pending_qty
			pending_item.amount = pending_qty * flt(item.rate)

			pending_item.base_amount = (
				pending_qty * flt(item.base_rate)
			)

			pending_items.append(pending_item)

		if not pending_items:
			continue

		order.items = pending_items
		order.total_qty = sum(
			flt(item.qty)
			for item in pending_items
		)

		order.total = sum(
			flt(item.amount)
			for item in pending_items
		)

		order.net_total = order.total
		order.grand_total = order.total
		orders.append(order)

		if order.transaction_date:
			dates.append(order.transaction_date)

		grand_total += flt(order.grand_total)

		if currency is None:
			currency = order.currency
		elif currency != order.currency:
			currency = None

	if not orders:
		frappe.throw(_("None of the selected Sales Orders have pending items."))

	dates.sort()
	date_heading = get_date_heading(dates)

	return frappe.render_template(
		"srv_erp/templates/order_slip_ledger.html",
		{
			"orders": orders,
			"date_heading": date_heading,
			"grand_total": grand_total,
			"currency": currency,
			"pending_only": True,
		},
	)

 
 
 
@frappe.whitelist()
def get_required_stock_html(names: list[str] | str) -> str:
	names = parse_order_names(names)

	if not names:
		frappe.throw(_("Select at least one Sales Order."))

	if len(names) > MAX_ORDERS_PER_PRINT:
		frappe.throw(
			_("You can print up to {0} Sales Orders at a time.").format(MAX_ORDERS_PER_PRINT)
		)

	required_items = {}
	dates = []

	for name in names:
		order = frappe.get_doc("Sales Order", name)
		order.check_permission("print")

		if order.transaction_date:
			dates.append(order.transaction_date)

		for item in order.items:
			ordered_qty = flt(item.qty)
			delivered_qty = flt(item.delivered_qty)
			pending_qty = ordered_qty - delivered_qty

			if pending_qty <= 0:
				continue

			uom = item.uom or item.stock_uom
			key = (item.item_code, uom)

			if key not in required_items:
				required_items[key] = {
					"item_code": item.item_code,
					"item_name": item.item_name,
					"item_group": item.item_group,
					"uom": uom,
					"qty": 0,
				}

			required_items[key]["qty"] += pending_qty

	if not required_items:
		frappe.throw(
			_("None of the selected Sales Orders have pending items.")
		)

	print(f"required items: \n{required_items}")
	item_groups = {}

	for item in required_items.values():
		item_group = item["item_group"] or _("No Item Group")
		item_groups.setdefault(item_group, []).append(item)

	for items in item_groups.values():
		items.sort(
			key=lambda item: (
				(item["item_name"] or "").lower(),
				item["item_code"],
				item["uom"],
			)
		)

	item_groups = dict(
		sorted(
			item_groups.items(),
			key=lambda group: group[0].lower(),
		)
	)

	dates.sort()
	date_heading = get_date_heading(dates)
	company = frappe.defaults.get_user_default("Company")
	
	return frappe.render_template(
		"srv_erp/templates/required_stock.html",
		{
			"item_groups": item_groups,
			"date_heading": date_heading,
			"sales_orders": names,
			"company": company,
   			"required_items_count": len(required_items),
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
