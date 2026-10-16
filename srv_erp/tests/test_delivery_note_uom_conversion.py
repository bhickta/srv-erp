from unittest import TestCase
from unittest.mock import patch

import frappe
from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order
from erpnext.stock.doctype.item.test_item import make_item
from frappe.tests.utils import FrappeTestCase

from srv_erp.package_barcode.service import PackageBarcodeError
from srv_erp.selling.delivery_note import (
	are_delivery_items_compatible,
	get_delivery_scan_sales_order_items,
	make_delivery_note,
	reconcile_delivery_quantities,
	resolve_delivery_uom_conversion,
	validate_delivery_sales_order_quantities,
)


class TestDeliveryConversion(TestCase):
	def test_reject_nonpositive_factor(self):
		with patch("srv_erp.package_barcode.service.get_item_uom_conversion_factor", return_value=0):
			with self.assertRaises(frappe.ValidationError):
				resolve_delivery_uom_conversion("ITEM", "Box")


class TestDeliveryNoteUOMConversion(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = "_Test DN UOM Company"
		cls.customer = "_Test DN UOM Customer"
		if not frappe.db.exists("Company", cls.company):
			frappe.get_doc(
				dict(
					doctype="Company",
					company_name=cls.company,
					abbr="DNU",
					country="India",
					default_currency="INR",
					chart_of_accounts="Standard",
					enable_perpetual_inventory=0,
				)
			).insert()
		if not frappe.db.exists("Customer Group", "_Test DN Customers"):
			frappe.get_doc(
				dict(
					doctype="Customer Group",
					customer_group_name="_Test DN Customers",
					parent_customer_group="All Customer Groups",
					is_group=0,
				)
			).insert()
		if not frappe.db.exists("Territory", "_Test DN Territory"):
			frappe.get_doc(
				dict(
					doctype="Territory",
					territory_name="_Test DN Territory",
					parent_territory="All Territories",
					is_group=0,
				)
			).insert()
		if not frappe.db.exists("Customer", cls.customer):
			frappe.get_doc(
				dict(
					doctype="Customer",
					customer_name=cls.customer,
					customer_type="Company",
					customer_group="_Test DN Customers",
					territory="_Test DN Territory",
				)
			).insert()
		cls.operator = "dn-operator@example.com"
		if not frappe.db.exists("User", cls.operator):
			frappe.get_doc(
				dict(
					doctype="User",
					email=cls.operator,
					first_name="DN Operator",
					send_welcome_email=0,
					roles=[{"role": role} for role in ("Sales User", "Stock User", "Sales Manager")],
				)
			).insert()
		cls.warehouse = "Stores - DNU"
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.item = make_item(
			"_Test DN UOM Item",
			properties={"stock_uom": "Nos", "is_stock_item": 0},
			uoms=[{"uom": "Box", "conversion_factor": 20}],
		)
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_default_qty_entry_rule", "Allow Manual Qty"
		)
		if frappe.get_meta("SRV Settings").has_field("enable_sales_order_item_approval"):
			frappe.db.set_single_value("SRV Settings", "enable_sales_order_item_approval", 0)
		for workflow in frappe.get_all(
			"Workflow", filters={"document_type": "Sales Order", "is_active": 1}, pluck="name"
		):
			frappe.db.set_value("Workflow", workflow, "is_active", 0)
		frappe.clear_cache(doctype="Workflow")

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_cache()
		frappe.set_user("Administrator")

	def order(self, qty=10):
		return make_sales_order(
			item_code=self.item.name,
			qty=qty,
			uom="Box",
			rate=200,
			company=self.company,
			customer=self.customer,
			warehouse=self.warehouse,
		)

	def delivery(self, so, box_qty=9, pcs_qty=3):
		dn = make_delivery_note(so.name)
		dn.items[0].qty = box_qty
		if pcs_qty:
			row = dn.items[0].as_dict()
			for key in ("name", "parent", "parenttype", "parentfield", "idx"):
				row.pop(key, None)
			row.update(qty=pcs_qty, uom="Nos", conversion_factor=1, rate=10)
			dn.append("items", row)
		return dn

	def test_configured_and_unknown_uoms(self):
		self.assertEqual(resolve_delivery_uom_conversion(self.item.name, "Box"), ("Nos", 20))
		self.assertEqual(resolve_delivery_uom_conversion(self.item.name, "Nos"), ("Nos", 1))
		with self.assertRaises(PackageBarcodeError):
			resolve_delivery_uom_conversion(self.item.name, "Kg")

	def test_fractional_delivery_quantity_is_rejected(self):
		for uom in ("Box", "Nos"):
			dn = self.delivery(self.order(qty=3), box_qty=0.5, pcs_qty=0)
			dn.items[0].uom = uom
			with self.assertRaisesRegex(frappe.ValidationError, "whole number"):
				dn.insert()

	def test_whole_box_and_piece_rows_keep_their_uom(self):
		dn = self.delivery(self.order(qty=3), box_qty=1, pcs_qty=10).insert()
		self.assertEqual([row.stock_qty for row in dn.items], [20, 10])
		self.assertEqual([row.qty for row in dn.items], [1, 10])

	def test_mixed_rows_submit_and_cancel_update_order(self):
		so = self.order()
		dn = self.delivery(so)
		dn.insert()
		dn.submit()
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 9.15)
		self.assertEqual(so.delivery_status, "Partly Delivered")
		self.assertAlmostEqual(so.per_delivered, 91.5)
		dn.cancel()
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 0)

	def test_exact_delivery_and_over_delivery(self):
		so = self.order()
		dn = self.delivery(so, pcs_qty=20)
		dn.insert().submit()
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 10)
		self.assertEqual(so.delivery_status, "Fully Delivered")
		with self.assertRaises(frappe.ValidationError):
			excess = self.delivery(self.order(), pcs_qty=21)
			reconcile_delivery_quantities(excess)
			validate_delivery_sales_order_quantities(excess)

	def test_previous_partial_delivery_reduces_pending(self):
		so = self.order()
		self.delivery(so).insert().submit()
		with self.assertRaises(frappe.ValidationError):
			excess = self.delivery(so, box_qty=1, pcs_qty=0)
			reconcile_delivery_quantities(excess)
			validate_delivery_sales_order_quantities(excess)
		self.delivery(so, box_qty=0, pcs_qty=17).insert().submit()
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 10)

	def test_zero_draft_preserved_and_all_zero_submit_rejected(self):
		dn = make_delivery_note(self.order().name)
		dn.insert()
		self.assertEqual(dn.items[0].qty, 0)
		with self.assertRaises(frappe.ValidationError):
			dn.submit()

	def test_zero_rows_removed_and_reference_preserved(self):
		so = self.order()
		dn = self.delivery(so, box_qty=0)
		dn.insert().submit()
		self.assertEqual(len(dn.items), 1)
		self.assertEqual(dn.items[0].against_sales_order, so.name)
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 0.15)

	def test_foreign_line_is_rejected(self):
		dn = self.delivery(self.order(), box_qty=1, pcs_qty=0)
		dn.items[0].so_detail = self.order().items[0].name
		with self.assertRaises(frappe.ValidationError):
			dn.insert()

	def test_scan_candidates_include_pending_reference(self):
		so = self.order()
		lines = get_delivery_scan_sales_order_items(so.customer, so.company, self.item.name)
		self.assertTrue(
			any(line["so_detail"] == so.items[0].name and line["pending_stock_qty"] == 200 for line in lines)
		)

	def test_invoice_from_mixed_delivery_preserves_quantity_and_accounting(self):
		from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

		so = self.order()
		dn = self.delivery(so).insert().submit()
		invoice = make_sales_invoice(dn.name)
		invoice.insert().submit()
		self.assertEqual([row.uom for row in invoice.items], ["Box", "Nos"])
		self.assertEqual([row.qty for row in invoice.items], [9, 3])
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 9.15)
		invoice.cancel()

	def test_stock_invoice_does_not_recount_mixed_delivery_as_raw_qty(self):
		from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

		so = self.order()
		self.delivery(so, box_qty=8).insert().submit()
		invoice = make_sales_invoice(so.name)
		invoice.update_stock = 1
		invoice.items[0].qty = 1
		invoice.insert().submit()
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 9.15)
		invoice.cancel()
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 8.15)

	def test_scan_reference_required_on_server(self):
		self.order()
		dn = self.delivery(self.order(), box_qty=1, pcs_qty=0)
		dn.items[0].against_sales_order = None
		dn.items[0].so_detail = None
		with patch("srv_erp.package_barcode.service.validate_stock_transaction"):
			dn.items[0].barcode = "scanned-item"
			with self.assertRaises(frappe.ValidationError):
				dn.insert()

	def test_split_delivery_can_be_invoiced(self):
		from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

		so = self.order(qty=3)
		dn = self.delivery(so, box_qty=1, pcs_qty=40).insert().submit()
		invoice = make_sales_invoice(dn.name).insert().submit()
		self.assertEqual([row.qty for row in invoice.items], [1, 40])
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 3)

	def test_normal_operator_can_resolve_and_submit_delivery(self):
		so = self.order()
		frappe.set_user(self.operator)
		lines = get_delivery_scan_sales_order_items(so.customer, so.company, self.item.name)
		self.assertTrue(any(line["so_detail"] == so.items[0].name for line in lines))
		dn = self.delivery(so).insert().submit()
		self.assertEqual(dn.docstatus, 1)

	def test_scan_candidates_require_sales_order_read_permission(self):
		so = self.order()
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_delivery_scan_sales_order_items(so.customer, so.company, self.item.name)

	def test_whole_number_stock_uom_still_rejects_fractional_pieces(self):
		dn = self.delivery(self.order(), box_qty=0.01, pcs_qty=0)
		with self.assertRaises(frappe.ValidationError):
			dn.insert()

	def test_stock_ledger_uses_stock_qty_and_cancel_restores_bin(self):
		self.item = make_item(
			"_Test DN Stock UOM Item",
			properties={
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"item_defaults": [{"company": self.company, "default_warehouse": self.warehouse}],
			},
			uoms=[{"uom": "Box", "conversion_factor": 20}],
		)
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
		dn = self.delivery(self.order(qty=2), box_qty=1, pcs_qty=10)
		for row in dn.items:
			row.allow_zero_valuation_rate = 1
		dn.insert().submit()
		self.assertEqual(
			frappe.db.get_value(
				"Bin", {"item_code": self.item.name, "warehouse": self.warehouse}, "actual_qty"
			),
			-30,
		)
		dn.cancel()
		self.assertEqual(
			frappe.db.get_value(
				"Bin", {"item_code": self.item.name, "warehouse": self.warehouse}, "actual_qty"
			),
			0,
		)

	def variants(self, stock=False):
		from erpnext.controllers.item_variant import create_variant

		attribute = "_Test DN Dispatch Colour"
		if not frappe.db.exists("Item Attribute", attribute):
			frappe.get_doc(
				dict(
					doctype="Item Attribute",
					attribute_name=attribute,
					item_attribute_values=[
						{"attribute_value": "Red", "abbr": "R"},
						{"attribute_value": "Blue", "abbr": "B"},
					],
				)
			).insert()
		template = make_item(
			"_Test DN Dispatch Template" + (" Stock" if stock else ""),
			properties={
				"has_variants": 1,
				"stock_uom": "Nos",
				"is_stock_item": int(stock),
				"attributes": [{"attribute": attribute}],
				"item_defaults": [{"company": self.company, "default_warehouse": self.warehouse}],
			},
			uoms=[{"uom": "Box", "conversion_factor": 20}],
		)
		result = []
		for colour in ("Red", "Blue"):
			variant = create_variant(template.name, {attribute: colour})
			if frappe.db.exists("Item", variant.item_code):
				variant = frappe.get_doc("Item", variant.item_code)
			else:
				with patch.dict(frappe.flags, {"dynamic_item_service": True}):
					variant.insert()
			result.append(variant)
		return result

	def substituted_delivery(self, so, variant, pcs_qty=3):
		dn = self.delivery(so, box_qty=0, pcs_qty=pcs_qty)
		row = dn.items[-1]
		row.item_code = variant.name
		row.item_name = variant.item_name
		return dn

	def test_sibling_variant_fulfills_original_line_and_cancellation_restores_pending(self):
		ordered, dispatched = self.variants()
		self.item = ordered
		so = self.order(qty=2)
		dn = self.substituted_delivery(so, dispatched, pcs_qty=3).insert().submit()
		so.reload()
		self.assertEqual(so.items[0].item_code, ordered.name)
		self.assertEqual(dn.items[0].item_code, dispatched.name)
		self.assertAlmostEqual(so.items[0].delivered_qty, 0.15)
		self.assertAlmostEqual((so.items[0].qty - so.items[0].delivered_qty) * 20, 37)
		dn.cancel()
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 0)

	def test_sibling_scan_candidates_identify_ordered_variant(self):
		ordered, dispatched = self.variants()
		self.item = ordered
		so = self.order()
		lines = get_delivery_scan_sales_order_items(so.customer, so.company, dispatched.name)
		line = next(line for line in lines if line["so_detail"] == so.items[0].name)
		self.assertTrue(line["is_substitution"])
		self.assertEqual(line["item_code"], ordered.name)

	def test_unrelated_item_cannot_fulfill_variant_order(self):
		ordered, _ = self.variants()
		unrelated = self.item
		self.item = ordered
		with self.assertRaisesRegex(frappe.ValidationError, "same template"):
			self.substituted_delivery(self.order(), unrelated).insert()

	def test_different_template_variant_is_rejected(self):
		ordered, _ = self.variants()
		other = frappe.copy_doc(frappe.get_doc("Item", ordered.variant_of))
		other.item_code = "_Test DN Unrelated Template"
		other.item_name = other.item_code
		other.insert()
		from erpnext.controllers.item_variant import create_variant

		with patch.dict(frappe.flags, {"dynamic_item_service": True}):
			variant = create_variant(other.name, {"_Test DN Dispatch Colour": "Blue"}).insert()
		self.item = ordered
		with self.assertRaisesRegex(frappe.ValidationError, "same template"):
			self.substituted_delivery(self.order(), variant).insert()

	def test_substitution_with_different_stock_uom_is_rejected(self):
		ordered, dispatched = self.variants()
		frappe.db.set_value("Item", dispatched.name, "stock_uom", "Kg")
		frappe.clear_document_cache("Item", dispatched.name)
		self.item = ordered
		self.assertFalse(are_delivery_items_compatible(ordered.name, dispatched.name))
		with self.assertRaises(frappe.ValidationError):
			self.substituted_delivery(self.order(), dispatched).insert()

	def test_substitution_invoice_preserves_actual_variant_and_fulfillment_link(self):
		from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

		ordered, dispatched = self.variants()
		self.item = ordered
		so = self.order()
		dn = self.substituted_delivery(so, dispatched).insert().submit()
		invoice = make_sales_invoice(dn.name).insert().submit()
		self.assertEqual(invoice.items[0].item_code, dispatched.name)
		self.assertEqual(invoice.items[0].so_detail, so.items[0].name)
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 0.15)
		invoice.cancel()
		dn.reload()
		dn.cancel()
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 0)

	def test_substitution_invoice_cannot_retarget_another_order(self):
		from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

		ordered, dispatched = self.variants()
		self.item = ordered
		dn = self.substituted_delivery(self.order(), dispatched).insert().submit()
		other = self.order()
		invoice = make_sales_invoice(dn.name)
		invoice.items[0].sales_order = other.name
		invoice.items[0].so_detail = other.items[0].name
		with self.assertRaisesRegex(frappe.ValidationError, "fulfillment link"):
			invoice.insert()

	def test_substitution_deducts_only_dispatched_variant_inventory(self):
		ordered, dispatched = self.variants(stock=True)
		self.item = ordered
		so = self.order(qty=2)
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
		dn = self.substituted_delivery(so, dispatched, pcs_qty=30)
		for row in dn.items:
			row.allow_zero_valuation_rate = 1

		def balance(item):
			return (
				frappe.db.get_value(
					"Bin", {"item_code": item.name, "warehouse": self.warehouse}, "actual_qty"
				)
				or 0
			)

		ordered_before = balance(ordered)
		dispatched_before = balance(dispatched)
		dn.insert().submit()

		self.assertEqual(balance(ordered), ordered_before)
		self.assertEqual(balance(dispatched), dispatched_before - 30)
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 1.5)
		dn.cancel()
		self.assertEqual(balance(dispatched), dispatched_before)
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 0)

	def test_original_and_substitute_rows_share_converted_fulfillment_total(self):
		ordered, dispatched = self.variants()
		self.item = ordered
		so = self.order()
		dn = self.substituted_delivery(so, dispatched)
		dn.items[0].qty = 9
		dn.insert().submit()
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 9.15)
		self.assertEqual([row.item_code for row in dn.items], [ordered.name, dispatched.name])
		self.assertEqual([row.qty for row in dn.items], [9, 3])

	def test_substitute_uses_its_own_package_conversion(self):
		ordered, dispatched = self.variants()
		frappe.db.set_value(
			"UOM Conversion Detail", {"parent": dispatched.name, "uom": "Box"}, "conversion_factor", 10
		)
		frappe.clear_document_cache("Item", dispatched.name)
		self.item = ordered
		so = self.order()
		dn = self.substituted_delivery(so, dispatched, pcs_qty=1)
		dn.items[-1].uom = "Box"
		dn.items[-1].rate = 100
		dn.insert().submit()
		self.assertEqual(dn.items[0].conversion_factor, 10)
		self.assertEqual(dn.items[0].stock_qty, 10)
		so.reload()
		self.assertEqual(so.items[0].delivered_qty, 0.5)

	def test_scanned_substitute_cannot_lose_its_sales_order_reference(self):
		ordered, dispatched = self.variants()
		self.item = ordered
		dn = self.substituted_delivery(self.order(), dispatched)
		dn.items[0].qty = 0
		dn.items[-1].against_sales_order = None
		dn.items[-1].so_detail = None
		dn.items[-1].barcode = "substitute-scan"
		with self.assertRaisesRegex(frappe.ValidationError, "Select the Sales Order line"):
			dn.insert()

	def test_normal_operator_can_submit_a_sibling_substitution(self):
		ordered, dispatched = self.variants()
		self.item = ordered
		so = self.order()
		frappe.set_user(self.operator)
		lines = get_delivery_scan_sales_order_items(so.customer, so.company, dispatched.name)
		self.assertTrue(
			any(line["so_detail"] == so.items[0].name and line["is_substitution"] for line in lines)
		)
		dn = self.substituted_delivery(so, dispatched).insert().submit()
		self.assertEqual(dn.docstatus, 1)

	def test_returns_are_not_reconciled(self):
		dn = self.delivery(self.order(), box_qty=-1, pcs_qty=0)
		dn.is_return = 1
		dn.items[0].stock_qty = -123
		reconcile_delivery_quantities(dn)
		self.assertEqual(dn.items[0].stock_qty, -123)
