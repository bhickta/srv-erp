frappe.provide("srv_erp.package_barcode");

srv_erp.package_barcode.receipt_printer = "Thermal Receipt Printer KP307-UEWB";
srv_erp.package_barcode.receipt_formats = {
	"Stock Entry": "Stock Entry Scan Receipt",
	"Delivery Note": "Delivery Note Scan Receipt",
};
srv_erp.package_barcode.browser_receipt_formats = {
	"Stock Entry": "Stock Entry Scan Receipt Browser",
	"Delivery Note": "Delivery Note Scan Receipt Browser",
};

srv_erp.package_barcode.stock_child_doctypes = new Set([
	"Stock Entry Detail",
	"Delivery Note Item",
	"Stock Reconciliation Item",
]);
srv_erp.package_barcode.stock_table_display = {
	loaded: false,
	show_item_name_before_item_code: false,
};
