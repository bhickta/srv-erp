from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from srv_erp.srv_erp.report.stock_inward_register.stock_inward_register import (
	GROUP_BY,
	add_group_rows,
	get_conditions,
	get_order_by,
	get_report_summary,
	set_batch_numbers,
	validate_filters,
)


class TestStockInwardRegister(TestCase):
	def setUp(self):
		translation_patcher = patch(
			"srv_erp.srv_erp.report.stock_inward_register.stock_inward_register._",
			side_effect=lambda value: value,
		)
		translation_patcher.start()
		self.addCleanup(translation_patcher.stop)
		self.filters = _dict(
			{
				"company": "Test Company",
				"from_date": "2026-09-01",
				"to_date": "2026-09-30",
			}
		)

	def test_base_conditions_only_include_submitted_inward_pr_and_se_rows(self):
		conditions = get_conditions(self.filters)
		self.assertIn("sle.actual_qty > 0", conditions)
		self.assertIn("sle.is_cancelled = 0", conditions)
		self.assertIn("sle.voucher_type IN ('Purchase Receipt', 'Stock Entry')", conditions)
		self.assertIn("COALESCE(pr.docstatus, se.docstatus) = 1", conditions)

	def test_supplier_and_tree_filters_cover_both_voucher_types(self):
		filters = self.filters.copy()
		filters.update(
			{
				"supplier": "Test Supplier",
				"supplier_group": "All Supplier Groups",
				"item_group": "All Item Groups",
				"warehouse": "All Warehouses - TC",
			}
		)
		conditions = " ".join(get_conditions(filters))
		self.assertIn("COALESCE(pr.supplier, se.supplier) = %(supplier)s", conditions)
		self.assertIn("supplier.supplier_group IN", conditions)
		self.assertIn("item.item_group IN", conditions)
		self.assertIn("sle.warehouse IN", conditions)

	def test_stock_entry_type_excludes_purchase_receipts(self):
		filters = self.filters.copy()
		filters.stock_entry_type = "Material Receipt"
		conditions = get_conditions(filters)
		self.assertIn("sle.voucher_type = 'Stock Entry'", conditions)
		self.assertIn("se.stock_entry_type = %(stock_entry_type)s", conditions)

	def test_batch_filter_supports_v15_serial_and_batch_bundles(self):
		filters = self.filters.copy()
		filters.batch_no = "BATCH-001"
		conditions = " ".join(get_conditions(filters))
		self.assertIn("sle.batch_no = %(batch_no)s", conditions)
		self.assertIn("tabSerial and Batch Entry", conditions)
		self.assertIn("sbe.parent = sle.serial_and_batch_bundle", conditions)

	@patch("srv_erp.srv_erp.report.stock_inward_register.stock_inward_register.frappe.get_all")
	def test_batch_numbers_are_loaded_without_splitting_ledger_rows(self, get_all):
		get_all.return_value = [
			_dict(parent="BUNDLE-1", batch_no="BATCH-1"),
			_dict(parent="BUNDLE-1", batch_no="BATCH-2"),
			_dict(parent="BUNDLE-1", batch_no="BATCH-2"),
		]
		rows = [_dict(batch_no=None, serial_and_batch_bundle="BUNDLE-1")]

		set_batch_numbers(rows)

		self.assertEqual(rows[0].batch_no, "BATCH-1, BATCH-2")
		self.assertEqual(len(rows), 1)

	def test_order_by_is_allowlisted_and_stable(self):
		filters = self.filters.copy()
		filters.update({"group_by": "Supplier", "sort_by": "Quantity", "sort_order": "Ascending"})
		self.assertEqual(
			get_order_by(filters),
			"supplier.supplier_name ASC, supplier.name ASC, sle.actual_qty ASC",
		)

	def test_item_group_orders_by_template_for_contiguous_grouping(self):
		filters = self.filters.copy()
		filters.update({"group_by": "Item", "sort_by": "Posting Date", "sort_order": "Descending"})
		self.assertEqual(
			get_order_by(filters),
			"item_template DESC, item.item_name DESC, sle.item_code DESC, "
			"sle.posting_date DESC, sle.posting_time DESC",
		)
		self.assertEqual(GROUP_BY["Item"][0], "item_template")

	def test_item_grouping_collapses_variants_under_template(self):
		rows = [
			_dict(item_template="TPL-1", in_qty=2, stock_uom="Kg", stock_value=20, company_currency="INR"),
			_dict(item_template="TPL-1", in_qty=3, stock_uom="Kg", stock_value=30, company_currency="INR"),
			_dict(item_template="TPL-2", in_qty=1, stock_uom="Kg", stock_value=5, company_currency="INR"),
		]

		grouped = add_group_rows(rows, "Item")

		group_rows = [row for row in grouped if row.get("is_group")]
		self.assertEqual([row.group_label for row in group_rows], ["TPL-1", "TPL-2"])
		self.assertEqual(group_rows[0].in_qty, 5)
		self.assertEqual(group_rows[0].stock_value, 50)
		self.assertEqual(group_rows[1].in_qty, 1)
		self.assertEqual(group_rows[1].stock_value, 5)

	@patch("srv_erp.srv_erp.report.stock_inward_register.stock_inward_register.frappe.throw")
	def test_rejects_unknown_sort_field(self, throw):
		filters = self.filters.copy()
		filters.sort_by = "sle.creation; DROP TABLE"
		validate_filters(filters)
		throw.assert_called_once()

	def test_group_totals_do_not_add_different_uoms(self):
		rows = [
			_dict(
				voucher_type="Stock Entry",
				voucher_no="MAT-1",
				voucher_group="Stock Entry: MAT-1",
				in_qty=10,
				stock_uom="Kg",
				stock_value=100,
				company_currency="INR",
			),
			_dict(
				voucher_type="Stock Entry",
				voucher_no="MAT-1",
				voucher_group="Stock Entry: MAT-1",
				in_qty=5,
				stock_uom="Nos",
				stock_value=75,
				company_currency="INR",
			),
		]
		grouped = add_group_rows(rows, "Voucher")
		self.assertIsNone(grouped[0].in_qty)
		self.assertIsNone(grouped[0].stock_uom)
		self.assertEqual(grouped[0].group_label, "Stock Entry: MAT-1 (Mixed UOM)")
		self.assertEqual(grouped[0].stock_value, 175)

	def test_summary_only_totals_quantity_for_one_uom(self):
		rows = [
			_dict(
				voucher_type="Purchase Receipt",
				voucher_no="PR-1",
				in_qty=2,
				stock_uom="Kg",
				stock_value=20,
				company_currency="INR",
			),
			_dict(
				voucher_type="Stock Entry",
				voucher_no="SE-1",
				in_qty=3,
				stock_uom="Kg",
				stock_value=30,
				company_currency="INR",
			),
		]
		summary = get_report_summary(rows)
		self.assertEqual(summary[2]["label"], "Inward Qty (Kg)")
		self.assertEqual(summary[2]["value"], 5)
		self.assertEqual(summary[3]["value"], 50)
