# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.stock.utils import add_additional_uom_columns


def add_selected_uom_columns(columns, data, include_uom):
	"""Add Stock Balance-style converted columns for fields marked as quantities."""
	if not include_uom or not data:
		return

	conversion_detail = frappe.qb.DocType("UOM Conversion Detail")
	conversion_factors = dict(
		frappe.qb.from_(conversion_detail)
		.select(conversion_detail.parent, conversion_detail.conversion_factor)
		.where(
			(conversion_detail.parenttype == "Item")
			& (conversion_detail.uom == include_uom)
			& (conversion_detail.parent.isin({row.item_code for row in data if row.item_code}))
		)
		.run()
	)

	add_additional_uom_columns(columns, data, include_uom, conversion_factors)

	# ERPNext inserts the alternate quantity immediately after Stock Qty. Keep the
	# native Qty/Stock UOM pair together, then show the selected-UOM quantity.
	fieldnames = [column.get("fieldname") for column in columns]
	if "stock_qty" in fieldnames and "stock_uom" in fieldnames:
		stock_uom_column = columns.pop(fieldnames.index("stock_uom"))
		stock_qty_index = next(
			index for index, column in enumerate(columns) if column.get("fieldname") == "stock_qty"
		)
		columns.insert(stock_qty_index + 1, stock_uom_column)
