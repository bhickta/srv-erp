import frappe
from frappe import _


def validate_no_pending_sales_order(doc, method=None):
	"""
	Prevent creation of a new Sales Order when the customer
	already has an active Sales Order that is not fully delivered.

	Cancelled Sales Orders are ignored.
	"""

	if not doc.is_new():
		return

	if not doc.customer:
		return

	pending_orders = frappe.get_all(
		"Sales Order",
		filters={
			"customer": doc.customer,
			"docstatus": 1,
			"delivery_status": ["!=", "Fully Delivered"],
		},
		fields=[
			"name",
			"transaction_date",
			"delivery_status",
			"grand_total",
		],
		order_by="transaction_date desc",
		limit=20,
	)

	if not pending_orders:
		return

	order_lines = []

	for order in pending_orders:
		order_lines.append(
			_(
				"{0} — {1} — {2}"
			).format(
				order.name,
				order.transaction_date,
				order.delivery_status,
			)
		)

	frappe.throw(
		_(
			"Cannot create a new Sales Order for <b>{0}</b> because "
			"the customer already has pending Sales Order(s)."
		).format(doc.customer)
		+
		"<br><br>"
		+
		"<br>".join(order_lines)
	)