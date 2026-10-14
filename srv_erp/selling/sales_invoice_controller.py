import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.stock_controller import StockController
from frappe import _
from frappe.utils import cint, flt

from srv_erp.selling.delivery_note_controller import DeliveryUOMMixin


class SRVSalesInvoice(DeliveryUOMMixin, SalesInvoice):
	def update_status_updater_args(self):
		super().update_status_updater_args()
		# Stock invoices also recalculate delivered_qty from existing Delivery Notes.
		for rule in self.status_updater:
			if rule.get("target_dt") == "Sales Order Item" and rule.get("target_field") == "delivered_qty":
				rule["source_field"] = (
					"stock_qty / nullif((select conversion_factor from `tabSales Order Item` where name = `tabSales Invoice Item`.so_detail), 0)"
				)
				rule["second_source_field"] = (
					"stock_qty / nullif((select conversion_factor from `tabSales Order Item` where name = `tabDelivery Note Item`.so_detail), 0)"
				)

	def validate_with_previous_doc(self):
		if self.is_return:
			return super().validate_with_previous_doc()
		for row in self.items:
			if row.so_detail and not row.dn_detail:
				line = frappe.db.get_value(
					"Sales Order Item", row.so_detail, ["uom", "conversion_factor"], as_dict=True
				)
				if line and (
					row.uom != line.uom or flt(row.conversion_factor) != flt(line.conversion_factor)
				):
					frappe.throw(
						_(
							"Row {0}: UOM must match the Sales Order unless invoiced from a Delivery Note."
						).format(row.idx)
					)
		StockController.validate_with_previous_doc(
			self,
			{
				"Sales Order": {
					"ref_dn_field": "sales_order",
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
				"Delivery Note": {
					"ref_dn_field": "delivery_note",
					"compare_fields": [
						["customer", "="],
						["company", "="],
						["project", "="],
						["currency", "="],
					],
				},
				"Delivery Note Item": {
					"ref_dn_field": "dn_detail",
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
				[["Sales Order", "sales_order", "so_detail"], ["Delivery Note", "delivery_note", "dn_detail"]]
			)
