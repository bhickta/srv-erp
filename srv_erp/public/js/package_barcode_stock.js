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

srv_erp.package_barcode.get_item_uom_details = function (item_code) {
	srv_erp.package_barcode.item_uom_details = srv_erp.package_barcode.item_uom_details || {};
	if (!srv_erp.package_barcode.item_uom_details[item_code]) {
		srv_erp.package_barcode.item_uom_details[item_code] = frappe
			.call({
				method: "srv_erp.package_barcode.api.get_item_uoms",
				args: { item_code },
			})
			.then((r) => r.message || {});
	}

	return srv_erp.package_barcode.item_uom_details[item_code];
};

srv_erp.package_barcode.apply_stock_reconciliation_package_uom = function (frm, row, data) {
	if (frm.doctype !== "Stock Reconciliation" || !row || !data?.uom) {
		return;
	}

	return srv_erp.package_barcode.get_item_uom_details(row.item_code).then((details) => {
		const conversion_factor = flt(details.conversion_factors?.[data.uom] || 0);
		if (!conversion_factor) {
			frappe.throw(__("UOM {0} is not configured for Item {1}.", [data.uom, row.item_code]));
		}

		const existing_package_qty = row.package_uom === data.uom ? flt(row.package_qty) : 0;
		const package_qty = existing_package_qty + flt(data.qty || 1);
		return frappe.model.set_value(row.doctype, row.name, {
			package_qty,
			package_uom: data.uom,
			package_conversion_factor: conversion_factor,
			qty: package_qty * conversion_factor,
		})
			.finally(() => {
				frm.cscript.barcode_scanner.stock_reconciliation_package_uom = null;
			});
	});
};

srv_erp.package_barcode.recalculate_stock_reconciliation_qty = function (frm, cdt, cdn) {
	if (frm.doctype !== "Stock Reconciliation" || frm.package_barcode_recalculating_uom) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row?.item_code || !row.package_uom) {
		return;
	}

	frm.package_barcode_recalculating_uom = true;
	srv_erp.package_barcode
		.get_item_uom_details(row.item_code)
		.then((details) => {
			const conversion_factor = flt(details.conversion_factors?.[row.package_uom] || 0);
			if (!conversion_factor) {
				frappe.throw(__("UOM {0} is not configured for Item {1}.", [row.package_uom, row.item_code]));
			}

			return frappe.model.set_value(cdt, cdn, {
				package_conversion_factor: conversion_factor,
				qty: flt(row.package_qty) * conversion_factor,
			});
		})
		.finally(() => {
			frm.package_barcode_recalculating_uom = false;
		});
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
	package_qty: srv_erp.package_barcode.recalculate_stock_reconciliation_qty,
	package_uom: srv_erp.package_barcode.recalculate_stock_reconciliation_qty,
});
