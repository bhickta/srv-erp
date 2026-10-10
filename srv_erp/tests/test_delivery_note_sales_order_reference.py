from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.selling.delivery_note import (
	get_open_sales_order_items,
	make_delivery_note as make_delivery_note_from_sales_order,
	validate_sales_order_reference,
)


def make_delivery_note(customer="CUST-0001", items=None, is_return=0):
	return frappe._dict(
		{
			"doctype": "Delivery Note",
			"customer": customer,
			"is_return": is_return,
			"items": [frappe._dict(row) for row in (items or [])],
		}
	)


def raise_validation_error(message, *args, **kwargs):
	raise frappe.ValidationError(message)


class TestDeliveryNoteSalesOrderReference(TestCase):
	@patch("erpnext.selling.doctype.sales_order.sales_order.make_delivery_note")
	def test_initial_sales_order_mapping_zeros_quantities(self, erpnext_make_delivery_note):
		doc = frappe._dict(
			items=[frappe._dict(qty=5, stock_qty=5)]
		)
		erpnext_make_delivery_note.return_value = doc

		result = make_delivery_note_from_sales_order("SO-0001")

		self.assertEqual(result["items"][0].qty, 0)
		self.assertEqual(result["items"][0].stock_qty, 0)
		erpnext_make_delivery_note.assert_called_once_with(
			"SO-0001", kwargs=None, target_doc=None
		)

	@patch("erpnext.selling.doctype.sales_order.sales_order.make_delivery_note")
	def test_get_items_mapping_zeros_new_rows_and_preserves_existing_quantities(
		self, erpnext_make_delivery_note
	):
		target_doc = frappe._dict(
			items=[frappe._dict(name="DN-ITEM-1", qty=2, stock_qty=2)]
		)
		doc = frappe._dict(
			items=[
				frappe._dict(name="DN-ITEM-1", qty=2, stock_qty=2),
				frappe._dict(name="DN-ITEM-2", qty=5, stock_qty=5),
			]
		)
		erpnext_make_delivery_note.return_value = doc

		result = make_delivery_note_from_sales_order("SO-0001", target_doc=target_doc)

		self.assertEqual(result["items"][0].qty, 2)
		self.assertEqual(result["items"][0].stock_qty, 2)
		self.assertEqual(result["items"][1].qty, 0)
		self.assertEqual(result["items"][1].stock_qty, 0)
		erpnext_make_delivery_note.assert_called_once_with(
			"SO-0001", kwargs=None, target_doc=target_doc
		)

	def test_linked_row_is_allowed_without_query(self):
		doc = make_delivery_note(
			items=[{"item_code": "ITEM-1", "against_sales_order": "SO-0001"}]
		)

		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			validate_sales_order_reference(doc)

		mock_frappe.db.sql.assert_not_called()

	def test_item_absent_from_open_sales_order_is_allowed(self):
		doc = make_delivery_note(items=[{"item_code": "ITEM-1"}])

		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			mock_frappe.db.sql.return_value = []
			validate_sales_order_reference(doc)

		mock_frappe.db.sql.assert_called_once()

	def test_item_pending_in_open_sales_order_must_reference_it(self):
		doc = make_delivery_note(
			items=[
				{"item_code": "ITEM-1"},
				{"item_code": "ITEM-2", "against_sales_order": "SO-0001"},
			]
		)

		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			mock_frappe.db.sql.return_value = [frappe._dict(item_code="ITEM-1")]
			mock_frappe.throw.side_effect = raise_validation_error
			with patch("srv_erp.selling.delivery_note._", side_effect=lambda value: value):
				with self.assertRaises(frappe.ValidationError):
					validate_sales_order_reference(doc)

		mock_frappe.throw.assert_called_once()

	def test_return_delivery_note_is_skipped(self):
		doc = make_delivery_note(is_return=1, items=[{"item_code": "ITEM-1"}])

		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			validate_sales_order_reference(doc)

		mock_frappe.db.sql.assert_not_called()

	def test_missing_customer_is_skipped(self):
		doc = make_delivery_note(customer=None, items=[{"item_code": "ITEM-1"}])

		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			validate_sales_order_reference(doc)

		mock_frappe.db.sql.assert_not_called()

	def test_get_open_sales_order_items_returns_distinct_codes(self):
		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			mock_frappe.db.sql.return_value = [
				frappe._dict(item_code="ITEM-1"),
				frappe._dict(item_code="ITEM-1"),
			]
			result = get_open_sales_order_items("CUST-0001", ["ITEM-1"])

		self.assertEqual(result, {"ITEM-1"})

	def test_get_open_sales_order_items_skips_empty_input(self):
		with patch("srv_erp.selling.delivery_note.frappe") as mock_frappe:
			self.assertEqual(get_open_sales_order_items(None, ["ITEM-1"]), set())
			self.assertEqual(get_open_sales_order_items("CUST-0001", []), set())

		mock_frappe.db.sql.assert_not_called()
