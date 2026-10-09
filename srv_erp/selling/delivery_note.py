import frappe
from frappe import _
from frappe.utils import flt

CLOSED_SALES_ORDER_STATUSES = ("Closed", "Completed")


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

	ordered_item_codes = get_open_sales_order_items(
		doc.customer, list(set(unlinked_item_codes))
	)

	offending = [
		item_code
		for item_code in dict.fromkeys(unlinked_item_codes)
		if item_code in ordered_item_codes
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

	if so.docstatus != 1:
		return []

	return [
		{
			"item_code": row.item_code,
			"so_detail": row.name,
			"against_sales_order": so.name,
			"qty": row.qty,
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
	print("override method calls")
	doc = erpnext_make_delivery_note(
		source_name,
		target_doc=target_doc,
		kwargs=kwargs,
	)

	for row in doc.get("items", []):
		print(row.name)
		row.qty = 0
		row.stock_qty = 0

	return doc


def remove_zero_quantity_items_on_submit(doc, method=None):
	if doc.get("_action") != "submit":
		return

	if doc.get("is_return"):
		return

	doc.items = [
		row for row in doc.items
		if row.get("qty") is None or row.qty != 0
	]

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
            frappe.throw(
                _("Your Delivery Note Does not have any item to dispatch.")
            )
    else:
        doc.flags.allow_zero_qty = True