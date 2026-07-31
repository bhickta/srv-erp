import frappe
from frappe.utils import cint

from erpnext.stock.report.stock_balance.stock_balance import StockBalanceReport, execute as erpnext_execute


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not cint(filters.get("exclude_disabled_items", 1)):
		return erpnext_execute(filters)

	return SRVStockBalanceReport(filters).run()


class SRVStockBalanceReport(StockBalanceReport):
	def apply_items_filters(self, query, item_table):
		query = super().apply_items_filters(query, item_table)
		return query.where(item_table.disabled == 0)

	def prepare_new_data(self):
		super().prepare_new_data()
		self.data = [row for row in self.data if not is_item_disabled(row.get("item_code"))]


def is_item_disabled(item_code):
	return cint(frappe.get_cached_value("Item", item_code, "disabled")) if item_code else 0
