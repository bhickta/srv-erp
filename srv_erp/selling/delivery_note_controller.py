import frappe
from erpnext.controllers.stock_controller import StockController
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote
from frappe.utils import cint, flt


class DeliveryUOMMixin:
	def validate_uom_is_integer(self, uom_field, qty_fields, child_dt=None):
		if self.is_return or uom_field != "uom" or qty_fields != "qty":
			return super().validate_uom_is_integer(uom_field, qty_fields, child_dt)
		from types import SimpleNamespace

		from erpnext.utilities.transaction_base import validate_uom_is_integer

		# Fractional packages are allowed; whole-number stock UOM rules still apply.
		rows = [
			row
			for row in self.get_all_children(parenttype=child_dt)
			if row.get("uom") == row.get("stock_uom")
			or (self.doctype == "Sales Invoice" and not row.get("dn_detail"))
		]
		validate_uom_is_integer(
			SimpleNamespace(get_all_children=lambda parenttype=None: rows), uom_field, qty_fields, child_dt
		)

	def validate_rate_with_reference_doc(self, ref_details):
		for reference in ref_details:
			if reference[0] != "Sales Order":
				super().validate_rate_with_reference_doc([reference])
				continue
			originals = []
			try:
				for row in self.items:
					if not row.so_detail:
						continue
					factor = frappe.db.get_value("Sales Order Item", row.so_detail, "conversion_factor")
					originals.append((row, row.rate))
					row.rate = flt(row.rate) * flt(factor) / flt(row.conversion_factor)
				super().validate_rate_with_reference_doc([reference])
			finally:
				for row, rate in originals:
					row.rate = rate


class SRVDeliveryNote(DeliveryUOMMixin, DeliveryNote):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# ERPNext sums row qty; mixed UOM rows must be expressed in the SO line UOM.
		for rule in self.status_updater:
			if rule.get("target_dt") == "Sales Order Item":
				rule["source_field"] = (
					"stock_qty / nullif((select conversion_factor from `tabSales Order Item` where name = `tabDelivery Note Item`.so_detail), 0)"
				)
				rule["second_source_field"] = (
					"stock_qty / nullif((select conversion_factor from `tabSales Order Item` where name = `tabSales Invoice Item`.so_detail), 0)"
				)

	def validate_with_previous_doc(self):
		if self.is_return:
			return super().validate_with_previous_doc()
		StockController.validate_with_previous_doc(
			self,
			{
				"Sales Order": {
					"ref_dn_field": "against_sales_order",
					"compare_fields": [
						["customer", "="],
						["company", "="],
						["project", "="],
						["currency", "="],
					],
				},
				"Sales Order Item": {
					"ref_dn_field": "so_detail",
					"compare_fields": [["item_code", "="]],
					"is_child_table": True,
					"allow_duplicate_prev_row_id": True,
				},
				"Sales Invoice": {
					"ref_dn_field": "against_sales_invoice",
					"compare_fields": [
						["customer", "="],
						["company", "="],
						["project", "="],
						["currency", "="],
					],
				},
				"Sales Invoice Item": {
					"ref_dn_field": "si_detail",
					"compare_fields": [["item_code", "="], ["uom", "="], ["conversion_factor", "="]],
					"is_child_table": True,
					"allow_duplicate_prev_row_id": True,
				},
			},
		)

		if (
			cint(frappe.db.get_single_value("Selling Settings", "maintain_same_sales_rate"))
			and not self.is_return
			and not self.is_internal_customer
		):
			self.validate_rate_with_reference_doc(
				[
					["Sales Order", "against_sales_order", "so_detail"],
					["Sales Invoice", "against_sales_invoice", "si_detail"],
				]
			)
