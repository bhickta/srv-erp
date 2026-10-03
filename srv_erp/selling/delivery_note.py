import frappe
from frappe import _

CLOSED_SALES_ORDER_STATUSES = ("Closed", "Completed")


def validate_sales_order_reference(doc, method=None):
	"""Require a Sales Order reference for items pending in an open Sales Order.

	When a Delivery Note row's item is still to be delivered against a
	submitted Sales Order of the same customer, the row must carry
	`against_sales_order` so the stock movement stays linked to the order it
	fulfils.
	"""
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
	"""Return the set of item codes pending in an open Sales Order."""
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
