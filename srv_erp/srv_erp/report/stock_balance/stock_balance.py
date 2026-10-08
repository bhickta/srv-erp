import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext.stock.report.stock_balance.stock_balance import StockBalanceReport, execute as erpnext_execute


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not cint(filters.get("exclude_disabled_items", 1)):
		columns, data = erpnext_execute(filters)
		add_maximum_stock_data(data)
		return add_maximum_stock_columns(columns), data

	return SRVStockBalanceReport(filters).run()


class SRVStockBalanceReport(StockBalanceReport):
	def apply_items_filters(self, query, item_table):
		query = super().apply_items_filters(query, item_table)
		return query.where(item_table.disabled == 0)

	def get_columns(self):
		return add_maximum_stock_columns(super().get_columns())

	def prepare_new_data(self):
		super().prepare_new_data()
		self.data = [row for row in self.data if not is_item_disabled(row.get("item_code"))]
		add_maximum_stock_data(self.data)


def add_maximum_stock_columns(columns):
	columns = [dict(column) for column in columns]
	if any(column.get("fieldname") == "maximum_stock" for column in columns):
		return columns

	insert_at = len(columns)
	for index, column in enumerate(columns):
		if column.get("fieldname") == "bal_qty":
			insert_at = index + 1
			break

	columns[insert_at:insert_at] = [
		{
			"label": _("Maximum Stock"),
			"fieldname": "maximum_stock",
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{
			"label": _("Over Max"),
			"fieldname": "over_max",
			"fieldtype": "Check",
			"width": 80,
		},
	]
	return columns


def add_maximum_stock_data(rows):
	item_codes = {row.get("item_code") for row in rows if row.get("item_code")}
	max_by_item = get_maximum_stock_map(item_codes)

	total_by_item = {}
	for row in rows:
		item_code = row.get("item_code")
		total_by_item[item_code] = total_by_item.get(item_code, 0.0) + flt(row.get("bal_qty"))

	for row in rows:
		item_code = row.get("item_code")
		maximum_stock = max_by_item.get(item_code, 0.0)
		row["maximum_stock"] = maximum_stock
		row["over_max"] = 1 if maximum_stock and total_by_item.get(item_code, 0.0) > maximum_stock else 0

	return rows


def get_maximum_stock_map(item_codes):
	if not item_codes:
		return {}

	rows = frappe.get_all(
		"Item",
		filters={"name": ("in", list(item_codes))},
		fields=["name", "maximum_stock"],
	)
	return {row.name: flt(row.maximum_stock) for row in rows}


def is_item_disabled(item_code):
	return cint(frappe.get_cached_value("Item", item_code, "disabled")) if item_code else 0
