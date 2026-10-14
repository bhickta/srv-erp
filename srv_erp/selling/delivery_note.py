import frappe
from frappe import _
from frappe.utils import flt

CLOSED_SALES_ORDER_STATUSES = ("Closed", "Completed")


def resolve_delivery_uom_conversion(item_code, uom):
	from srv_erp.package_barcode.service import get_item_uom_conversion_factor

	factor = get_item_uom_conversion_factor(item_code, uom)
	if factor <= 0:
		frappe.throw(_("UOM {0} has an invalid conversion factor for Item {1}.").format(uom, item_code))
	return frappe.get_cached_value("Item", item_code, "stock_uom"), factor


def reconcile_delivery_quantities(doc, method=None):
	if doc.get("is_return"):
		return
	for row in doc.get("items", []):
		if not row.item_code:
			continue
		if flt(row.qty) < 0:
			frappe.throw(_("Row {0}: Use a return Delivery Note for negative quantities.").format(row.idx))
		row.stock_uom, row.conversion_factor = resolve_delivery_uom_conversion(row.item_code, row.uom)
		row.stock_qty = flt(flt(row.qty) * row.conversion_factor, row.precision("stock_qty"))


def validate_delivery_sales_order_quantities(doc, method=None):
	if doc.get("is_return"):
		return
	scanned_items = {scan.item_code for scan in doc.get("package_barcodes", [])}
	validate_sales_order_reference(
		frappe._dict(
			customer=doc.customer,
			items=[
				row for row in doc.get("items", []) if row.item_code in scanned_items or row.get("barcode")
			],
		)
	)
	orders = {}
	for name in sorted(
		{row.against_sales_order for row in doc.get("items", []) if row.get("against_sales_order")}
	):
		# Lock orders in a stable order to serialize simultaneous submissions.
		orders[name] = frappe.get_doc("Sales Order", name, for_update=True)
	totals = {}
	for row in doc.get("items", []):
		if not row.get("against_sales_order") and not row.get("so_detail"):
			continue
		if not row.get("against_sales_order") or not row.get("so_detail"):
			frappe.throw(_("Row {0}: Select both the Sales Order and its item line.").format(row.idx))
		name = row.against_sales_order
		so = orders[name]
		line = next((line for line in so.items if line.name == row.so_detail), None)
		if (
			so.docstatus != 1
			or so.status in CLOSED_SALES_ORDER_STATUSES
			or so.customer != doc.customer
			or so.company != doc.company
			or not line
			or line.item_code != row.item_code
		):
			frappe.throw(
				_("Row {0}: Invalid Sales Order item reference for {1}.").format(row.idx, row.item_code)
			)
		key = (name, line.name)
		totals[key] = totals.get(key, 0) + flt(row.stock_qty)
		pending = (flt(line.qty) - flt(line.delivered_qty)) * flt(line.conversion_factor)
		if flt(totals[key] - pending, row.precision("stock_qty")) > 0:
			frappe.throw(
				_("Item {0}: delivery exceeds the pending quantity on Sales Order {1} ({2} {3}).").format(
					row.item_code, name, pending, row.stock_uom
				)
			)


@frappe.whitelist()
def get_delivery_scan_sales_order_items(customer, company, item_code):
	"""Only expose pending lines from orders the scanner is allowed to read."""
	orders = frappe.get_list(
		"Sales Order",
		filters={
			"customer": customer,
			"company": company,
			"docstatus": 1,
			"status": ("not in", CLOSED_SALES_ORDER_STATUSES),
		},
		pluck="name",
		limit_page_length=0,
	)
	return [
		line
		for name in orders
		for line in get_sales_order_items_for_delivery_note(name)
		if line["item_code"] == item_code and line["pending_stock_qty"] > 0
	]


def validate_sales_order_reference(doc, method=None):
	"""Require a Sales Order reference for items pending in an open Sales Order."""
	if doc.get("is_return"):
		return

	if not doc.get("customer"):
		return

	unlinked_item_codes = [
		row.item_code
		for row in doc.get("items", [])
		if row.get("item_code") and not row.get("against_sales_order")
	]

	if not unlinked_item_codes:
		return

	ordered_item_codes = get_open_sales_order_items(doc.customer, list(set(unlinked_item_codes)))

	offending = [
		item_code for item_code in dict.fromkeys(unlinked_item_codes) if item_code in ordered_item_codes
	]

	if not offending:
		return

	frappe.throw(
		_(
			"The following item(s) are pending in an open Sales Order for "
			"customer <b>{0}</b> and must be delivered against that Sales "
			"Order:<br>{1}"
		).format(
			doc.customer,
			"<br>".join(f"<b>{item_code}</b>" for item_code in offending),
		),
		title=_("Sales Order Reference Required"),
	)


def get_open_sales_order_items(customer, item_codes):
	"""Return the set of item codes pending in an open Sales Order.s"""
	if not customer or not item_codes:
		return set()

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT soi.item_code
		FROM `tabSales Order Item` soi
		INNER JOIN `tabSales Order` so ON so.name = soi.parent
		WHERE so.docstatus = 1
			AND so.customer = %(customer)s
			AND so.status NOT IN %(closed_statuses)s
			AND IFNULL(so.delivery_status, '') != 'Fully Delivered'
			AND soi.item_code IN %(item_codes)s
		""",
		{
			"customer": customer,
			"closed_statuses": CLOSED_SALES_ORDER_STATUSES,
			"item_codes": tuple(item_codes),
		},
		as_dict=True,
	)

	return {row.item_code for row in rows}


@frappe.whitelist()
def get_sales_order_items_for_delivery_note(sales_order):
	"""Return Sales Order item references for Delivery Note item mapping."""
	if not sales_order:
		return []

	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")

	if so.docstatus != 1:
		return []

	return [
		{
			"item_code": row.item_code,
			"so_detail": row.name,
			"against_sales_order": so.name,
			"qty": row.qty,
			"pending_stock_qty": max(0, (flt(row.qty) - flt(row.delivered_qty)) * flt(row.conversion_factor)),
			"uom": row.uom,
			"stock_uom": row.stock_uom,
			"conversion_factor": row.conversion_factor,
			"warehouse": row.warehouse,
		}
		for row in so.items
		if row.item_code
	]


@frappe.whitelist()
def make_delivery_note(source_name, target_doc=None, kwargs=None):
	from erpnext.selling.doctype.sales_order.sales_order import (
		make_delivery_note as erpnext_make_delivery_note,
	)

	existing_target_doc = frappe.parse_json(target_doc) if isinstance(target_doc, str) else target_doc
	existing_item_names = {
		row.get("name") for row in (existing_target_doc or {}).get("items", []) if row.get("name")
	}

	doc = erpnext_make_delivery_note(
		source_name,
		target_doc=target_doc,
		kwargs=kwargs,
	)

	for row in doc.get("items", []):
		if row.get("name") not in existing_item_names:
			row.qty = 0
			row.stock_qty = 0

	return doc


def remove_zero_quantity_items_on_submit(doc, method=None):
	if doc.get("_action") != "submit":
		return

	if doc.get("is_return"):
		return

	doc.items = [row for row in doc.items if row.get("qty") is None or row.qty != 0]

	if not doc.items:
		frappe.throw(
			_("Cannot submit a Delivery Note without any items having a non-zero quantity."),
			title=_("No Items to Deliver"),
		)


def prepare_delivery_note_quantities(doc, method=None):
	if doc.get("is_return"):
		return

	if doc.get("_action") == "submit":
		doc.set(
			"items",
			[row for row in doc.items if flt(row.qty) != 0],
		)

		if not doc.items:
			frappe.throw(_("Your Delivery Note Does not have any item to dispatch."))
	else:
		doc.flags.allow_zero_qty = True
