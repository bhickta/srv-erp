from frappe.model.document import Document


class SRVSettings(Document):
	def on_update(self):
		from srv_erp.grid_column_templates import clear_grid_column_template_boot_cache
		from srv_erp.selling.sales_order_ui import (
			configure_sales_order_current_stock_field,
			configure_sales_order_pending_qty_field,
		)

		configure_sales_order_pending_qty_field(self.show_pending_qty_in_sales_order)
		configure_sales_order_current_stock_field(self.show_current_stock_in_sales_order)
		clear_grid_column_template_boot_cache()
