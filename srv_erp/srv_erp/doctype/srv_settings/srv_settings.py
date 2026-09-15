import frappe
from frappe import _
from frappe.model.document import Document


class SRVSettings(Document):
	def validate(self):
		price_list = self.get("stock_entry_price_list")
		if price_list and not frappe.db.get_value("Price List", price_list, "enabled"):
			frappe.throw(_("Stock Entry Price List must be enabled."))

	def on_update(self):
		from srv_erp.grid_column_templates import clear_grid_column_template_boot_cache
		from srv_erp.selling.sales_order_ui import (
			configure_sales_order_current_stock_field,
			configure_sales_order_pending_qty_field,
		)

		configure_sales_order_pending_qty_field(self.show_pending_qty_in_sales_order)
		configure_sales_order_current_stock_field(self.show_current_stock_in_sales_order)
		clear_grid_column_template_boot_cache()
