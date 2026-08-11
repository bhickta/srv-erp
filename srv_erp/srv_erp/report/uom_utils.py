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
	if not conversion_factors:
		return

	convertible_fields = [
		column.get("fieldname") for column in columns if column.get("convertible") == "qty"
	]
	add_additional_uom_columns(columns, data, include_uom, conversion_factors)

	for fieldname in convertible_fields:
		alternate_fieldname = f"{fieldname}_alt"
		uom_fieldname = f"uom_{fieldname}"
		alternate_uom_fieldname = f"uom_{alternate_fieldname}"
		alternate_index = next(
			index
			for index, column in enumerate(columns)
			if column.get("fieldname") == alternate_fieldname
		)
		alternate_column = columns.pop(alternate_index)
		uom_index = next(
			index for index, column in enumerate(columns) if column.get("fieldname") == uom_fieldname
		)
		columns[uom_index + 1 : uom_index + 1] = [
			alternate_column,
			{
				"label": "UOM",
				"fieldname": alternate_uom_fieldname,
				"fieldtype": "Link",
				"options": "UOM",
				"width": 90,
			},
		]
		for row in data:
			row[alternate_uom_fieldname] = include_uom
