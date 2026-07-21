frappe.provide("srv_erp.package_barcode");

srv_erp.package_barcode.stock_child_doctypes = new Set([
	"Stock Entry Detail",
	"Delivery Note Item",
	"Stock Reconciliation Item",
]);
srv_erp.package_barcode.stock_table_display = {
	loaded: false,
	show_item_name_before_item_code: false,
};
