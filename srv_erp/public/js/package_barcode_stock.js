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
	srv_erp.package_barcode.add_scan_receipt_button(frm);
};

srv_erp.package_barcode.add_scan_receipt_button = function (frm) {
	const print_format = srv_erp.package_barcode.receipt_formats[frm.doctype];
	if (!print_format) {
		return;
	}

	frm.add_custom_button(
		__("Print Scan Receipt"),
		() => srv_erp.package_barcode.print_scan_receipt(frm, print_format),
		__("Package Barcode")
	);
	frm.add_custom_button(
		__("Print Scan Receipt (Browser)"),
		() => srv_erp.package_barcode.print_scan_receipt_in_browser(frm),
		__("Package Barcode")
	);
};

srv_erp.package_barcode.print_scan_receipt_in_browser = async function (frm) {
	if (!(frm.doc.items || []).some((row) => row.item_code)) {
		frappe.msgprint(__("Scan at least one item before printing the receipt."));
		return;
	}

	const print_window = window.open("", "_blank");
	if (!print_window) {
		frappe.msgprint(__("Please allow pop-ups to use browser printing."));
		return;
	}

	try {
		if (frm.is_dirty()) {
			await frm.save();
		}

		const print_format = srv_erp.package_barcode.browser_receipt_formats[frm.doctype];
		const query = new URLSearchParams({
			doctype: frm.doctype,
			name: frm.doc.name,
			format: print_format,
			no_letterhead: "1",
			trigger_print: "1",
		});
		print_window.location = `/printview?${query.toString()}`;
	} catch (error) {
		print_window.close();
		throw error;
	}
};

srv_erp.package_barcode.print_scan_receipt = async function (frm, print_format) {
	if (!(frm.doc.items || []).some((row) => row.item_code)) {
		frappe.msgprint(__("Scan at least one item before printing the receipt."));
		return;
	}

	if (frm.is_dirty()) {
		await frm.save();
	}

	frappe.dom.freeze(__("Preparing scan receipt..."));
	try {
		const result = await frappe.call({
			method: "frappe.www.printview.get_rendered_raw_commands",
			args: {
				doc: frm.doc,
				print_format,
			},
		});
		const commands = result.message && result.message.raw_commands;
		if (!commands) {
			throw new Error(__("The scan receipt could not be rendered."));
		}

		await frappe.ui.form.qz_connect();
		const printer = srv_erp.package_barcode.receipt_printer;
		const config = qz.configs.create(printer, { encoding: "UTF-8" });
		await qz.print(config, [commands]);
		frappe.show_alert({
			message: __("Scan receipt sent to {0}", [printer]),
			indicator: "green",
		});
	} catch (error) {
		frappe.ui.form.qz_fail(error);
	} finally {
		frappe.dom.unfreeze();
	}
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

srv_erp.package_barcode.refresh_stock_reconciliation_package_row = function (frm, cdt, cdn) {
	if (frm.doctype !== "Stock Reconciliation") {
		return;
	}

	if (frm.events?.set_amount_quantity) {
		frm.events.set_amount_quantity(frm, cdt, cdn);
	}

	frm.refresh_field("items");
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
		const scanned_package_qty = flt(data.qty || 1);
		const scanned_stock_qty = scanned_package_qty * conversion_factor;
		const scanner = frm.cscript.barcode_scanner;
		const row_state = scanner?.stock_reconciliation_scan_row_state?.name === row.name
			? scanner.stock_reconciliation_scan_row_state
			: null;
		const previous_qty = row_state ? flt(row_state.qty) : flt(row.qty) - scanned_package_qty;
		const previous_package_qty = row_state ? flt(row_state.package_qty) : existing_package_qty;
		const previous_package_uom = row_state ? row_state.package_uom : row.package_uom;
		const previous_conversion_factor = row_state
			? flt(row_state.package_conversion_factor)
			: flt(row.package_conversion_factor);
		const previous_package_stock_qty = previous_package_qty * previous_conversion_factor;
		const can_keep_package_fields =
			(!previous_qty || previous_qty === previous_package_stock_qty) &&
			(!previous_package_uom || previous_package_uom === data.uom);
		const package_qty = can_keep_package_fields ? previous_package_qty + scanned_package_qty : 0;
		const stock_qty = can_keep_package_fields
			? package_qty * conversion_factor
			: previous_qty + scanned_stock_qty;

		frm.package_barcode_recalculating_uom = true;
		return frappe.run_serially([
			() => frappe.model.set_value(row.doctype, row.name, "package_uom", can_keep_package_fields ? data.uom : ""),
			() => frappe.model.set_value(row.doctype, row.name, "package_conversion_factor", can_keep_package_fields ? conversion_factor : 0),
			() => frappe.model.set_value(row.doctype, row.name, "package_qty", package_qty),
			() => frappe.model.set_value(row.doctype, row.name, "qty", stock_qty),
			() => srv_erp.package_barcode.refresh_stock_reconciliation_package_row(frm, row.doctype, row.name),
			() => {
				if (!can_keep_package_fields) {
					frappe.show_alert({
						message: __("Package fields were cleared because this row has mixed manual or package quantities."),
						indicator: "orange",
					});
				}
			},
		])
			.finally(() => {
				frm.package_barcode_recalculating_uom = false;
				if (scanner) {
					scanner.stock_reconciliation_scan_row_state = null;
				}
				frm.cscript.barcode_scanner.stock_reconciliation_package_uom = null;
			});
	});
};

srv_erp.package_barcode.recalculate_stock_reconciliation_qty = function (frm, cdt, cdn) {
	if (
		frm.doctype !== "Stock Reconciliation" ||
		frm.package_barcode_recalculating_uom ||
		frm.package_barcode_clearing_package_fields
	) {
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

			return frappe.run_serially([
				() => frappe.model.set_value(cdt, cdn, "package_conversion_factor", conversion_factor),
				() => frappe.model.set_value(cdt, cdn, "qty", flt(row.package_qty) * conversion_factor),
				() => srv_erp.package_barcode.refresh_stock_reconciliation_package_row(frm, cdt, cdn),
			]);
		})
		.finally(() => {
			frm.package_barcode_recalculating_uom = false;
		});
};

srv_erp.package_barcode.clear_stock_reconciliation_package_fields = function (frm, cdt, cdn) {
	if (
		frm.doctype !== "Stock Reconciliation" ||
		frm.package_barcode_recalculating_uom ||
		frm.package_barcode_clearing_package_fields
	) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row?.package_uom && !flt(row?.package_qty) && !flt(row?.package_conversion_factor)) {
		return;
	}

	frm.package_barcode_clearing_package_fields = true;
	frappe.run_serially([
		() => frappe.model.set_value(cdt, cdn, "package_qty", 0),
		() => frappe.model.set_value(cdt, cdn, "package_uom", ""),
		() => frappe.model.set_value(cdt, cdn, "package_conversion_factor", 0),
		() => srv_erp.package_barcode.refresh_stock_reconciliation_package_row(frm, cdt, cdn),
	])
		.then(() => {
			frappe.show_alert({
				message: __("Package fields were cleared because Stock Qty was edited manually."),
				indicator: "orange",
			});
		})
		.finally(() => {
			frm.package_barcode_clearing_package_fields = false;
		});
};

srv_erp.package_barcode.handle_stock_reconciliation_qty_change = function (frm, cdt, cdn) {
	if (frm.package_barcode_recalculating_uom) {
		return;
	}

	srv_erp.package_barcode.clear_stock_reconciliation_package_fields(frm, cdt, cdn);
	srv_erp.package_barcode.handle_qty_change(frm);
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
	qty: srv_erp.package_barcode.handle_stock_reconciliation_qty_change,
	package_qty: srv_erp.package_barcode.recalculate_stock_reconciliation_qty,
	package_uom: srv_erp.package_barcode.recalculate_stock_reconciliation_qty,
});
