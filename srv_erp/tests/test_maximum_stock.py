from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.srv_erp.report.maximum_stock_exceeded import maximum_stock_exceeded
from srv_erp.srv_erp.report.stock_balance import stock_balance


class TestMaximumStockExceededReport(TestCase):
	def test_columns(self):
		fieldnames = [column["fieldname"] for column in maximum_stock_exceeded.get_columns()]
		self.assertEqual(
			fieldnames,
			[
				"item_code",
				"item_name",
				"item_group",
				"stock_uom",
				"current_stock",
				"maximum_stock",
				"excess_qty",
			],
		)

	def _items(self):
		return [
			frappe._dict(item_code="A", item_name="A", item_group="G", stock_uom="Nos", maximum_stock=10),
			frappe._dict(item_code="B", item_name="B", item_group="G", stock_uom="Nos", maximum_stock=10),
			frappe._dict(item_code="C", item_name="C", item_group="G", stock_uom="Nos", maximum_stock=10),
		]

	def test_only_exceeded_filters_and_computes_excess(self):
		with (
			patch.object(maximum_stock_exceeded, "get_items_with_maximum_stock", return_value=self._items()),
			patch.object(
				maximum_stock_exceeded,
				"get_current_stock",
				return_value={"A": 25.0, "B": 10.0, "C": 0.0},
			),
		):
			data = maximum_stock_exceeded.get_data(frappe._dict({"only_exceeded": 1}))

		self.assertEqual([row["item_code"] for row in data], ["A"])
		self.assertEqual(data[0]["current_stock"], 25.0)
		self.assertEqual(data[0]["excess_qty"], 15.0)

	def test_all_items_when_only_exceeded_disabled(self):
		with (
			patch.object(maximum_stock_exceeded, "get_items_with_maximum_stock", return_value=self._items()),
			patch.object(
				maximum_stock_exceeded,
				"get_current_stock",
				return_value={"A": 25.0, "B": 10.0, "C": 0.0},
			),
		):
			data = maximum_stock_exceeded.get_data(frappe._dict({"only_exceeded": 0}))

		self.assertEqual([row["item_code"] for row in data], ["A", "B", "C"])
		self.assertEqual(data[0]["excess_qty"], 15.0)
		self.assertEqual(data[1]["excess_qty"], 0.0)
		self.assertEqual(data[2]["excess_qty"], -10.0)


class TestStockBalanceMaximumStock(TestCase):
	def test_columns_inserted_after_balance_qty_and_idempotent(self):
		base = [
			{"fieldname": "item_code"},
			{"fieldname": "bal_qty"},
			{"fieldname": "company"},
		]
		columns = stock_balance.add_maximum_stock_columns(base)
		fieldnames = [column["fieldname"] for column in columns]
		self.assertEqual(fieldnames, ["item_code", "bal_qty", "maximum_stock", "over_max", "company"])
		self.assertEqual(
			[column["fieldname"] for column in stock_balance.add_maximum_stock_columns(columns)],
			fieldnames,
		)

	def test_over_max_uses_item_total_across_rows(self):
		rows = [
			frappe._dict(item_code="A", bal_qty=60.0),
			frappe._dict(item_code="A", bal_qty=60.0),
			frappe._dict(item_code="B", bal_qty=5.0),
		]
		with patch.object(
			stock_balance,
			"get_maximum_stock_map",
			return_value={"A": 100.0, "B": 10.0},
		):
			stock_balance.add_maximum_stock_data(rows)

		self.assertEqual(rows[0]["maximum_stock"], 100.0)
		self.assertEqual(rows[0]["over_max"], 1)
		self.assertEqual(rows[1]["over_max"], 1)
		self.assertEqual(rows[2]["maximum_stock"], 10.0)
		self.assertEqual(rows[2]["over_max"], 0)
