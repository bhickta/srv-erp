srv_erp.package_barcode.setup_stock_scanner = function (frm) {
	if (!frm.cscript || !(erpnext && erpnext.utils && erpnext.utils.BarcodeScanner)) {
		return;
	}

	srv_erp.package_barcode.install_item_link_formatter();
	srv_erp.package_barcode.load_stock_table_display_settings(frm);

	const opts = { frm };
	if (frm.doc.doctype === "Stock Entry") {
		opts.warehouse_field = (doc) => {
			return doc.purpose === "Material Receipt" ? "t_warehouse" : "s_warehouse";
		};
	} else if (frm.doc.doctype === "Stock Reconciliation") {
		opts.uom_field = "stock_uom";
	}

	const barcode_scanner = new srv_erp.package_barcode.PackageBarcodeScanner(opts);
	frm.cscript.barcode_scanner = barcode_scanner;
	frm.barcode_scanner = barcode_scanner;
	srv_erp.package_barcode.render_scan_review(frm);
	srv_erp.package_barcode.refresh_barcode_only_items(frm);
};

frappe.ui.form.on("Stock Entry", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});

frappe.ui.form.on("Delivery Note", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});

frappe.ui.form.on("Stock Reconciliation", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});

frappe.ui.form.on("Stock Entry Detail", {
	item_code: srv_erp.package_barcode.handle_item_change,
	qty: srv_erp.package_barcode.handle_qty_change,
});

frappe.ui.form.on("Delivery Note Item", {
	item_code: srv_erp.package_barcode.handle_item_change,
	qty: srv_erp.package_barcode.handle_qty_change,
});

frappe.ui.form.on("Stock Reconciliation Item", {
	item_code: srv_erp.package_barcode.handle_item_change,
	qty: srv_erp.package_barcode.handle_qty_change,
});
