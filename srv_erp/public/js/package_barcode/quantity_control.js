srv_erp.package_barcode.get_qty_field = function () {
	return "qty";
};

srv_erp.package_barcode.get_item_codes = function (frm) {
	return [
		...new Set(
			(frm.doc.items || [])
				.map((row) => row.item_code)
				.filter(Boolean)
		),
	];
};

srv_erp.package_barcode.get_scanned_qty_by_item = function (frm) {
	const scanned_qty = {};
	(frm.doc.package_barcodes || []).forEach((row) => {
		if (row.item_code) {
			scanned_qty[row.item_code] = (scanned_qty[row.item_code] || 0) + 1;
		}
	});
	return scanned_qty;
};

srv_erp.package_barcode.refresh_barcode_only_items = function (frm) {
	const item_codes = srv_erp.package_barcode.get_item_codes(frm);
	if (!item_codes.length) {
		frm.package_barcode_only_items = new Set();
		return;
	}

	frappe.call({
		method: "srv_erp.package_barcode.api.get_barcode_only_items",
		args: { item_codes },
		callback(r) {
			frm.package_barcode_only_items = new Set(r.message || []);
			srv_erp.package_barcode.enforce_barcode_only_qty(frm);
		},
	});
};

srv_erp.package_barcode.enforce_barcode_only_qty = function (frm, notify = false) {
	if (frm.doctype === "Delivery Note") {
		if (!notify || frm.package_barcode_enforcing_qty || frm.package_barcode_delivery_scanning || frm.doc.is_return) return;
		return srv_erp.package_barcode.enforce_delivery_scan_qty(frm);
	}
	if (
		frm.doctype === "Stock Reconciliation" ||
		frm.doctype === "Delivery Note"
	) {
		return;
	}
	if (frm.package_barcode_enforcing_qty) {
		return;
	}

	const barcode_only_items = frm.package_barcode_only_items || new Set();
	if (!barcode_only_items.size) {
		return;
	}

	const qty_field = srv_erp.package_barcode.get_qty_field(frm);
	const scanned_qty = srv_erp.package_barcode.get_scanned_qty_by_item(frm);
	const updates = [];

	(frm.doc.items || []).forEach((row) => {
		if (!row.item_code || !barcode_only_items.has(row.item_code)) {
			return;
		}

		const expected_qty = scanned_qty[row.item_code] || 0;
		if (flt(row[qty_field]) !== expected_qty) {
			updates.push(frappe.model.set_value(row.doctype, row.name, qty_field, expected_qty));
		}
	});

	if (!updates.length) {
		return;
	}

	frm.package_barcode_enforcing_qty = true;
	Promise.all(updates).finally(() => {
		frm.package_barcode_enforcing_qty = false;
		if (notify) {
			frappe.show_alert({
				message: __("Qty is controlled by Package Barcode scans for this item."),
				indicator: "orange",
			});
		}
	});
};

srv_erp.package_barcode.handle_item_change = function (frm) {
	srv_erp.package_barcode.refresh_barcode_only_items(frm);
};

srv_erp.package_barcode.handle_qty_change = function (frm) {
	srv_erp.package_barcode.enforce_barcode_only_qty(frm, true);
};

// Several SO lines can share an item; never copy the whole scan total into each line.
srv_erp.package_barcode.enforce_delivery_scan_qty = async function (frm) {
	const items = frm.package_barcode_only_items || new Set();
	frm.package_barcode_enforcing_qty = true;
	try {
		for (const item_code of items) {
			const details = await srv_erp.package_barcode.get_item_uom_details(item_code);
			const scans = (frm.doc.package_barcodes || []).filter((row) => row.item_code === item_code);
			let stock_qty = 0;
			for (const scan of scans) {
				const factor = flt(details.conversion_factors[scan.uom]);
				if (factor <= 0) frappe.throw(__("UOM {0} is not configured for Item {1}.", [scan.uom, item_code]));
				stock_qty += factor;
			}
			const rows = (frm.doc.items || []).filter((row) => row.item_code === item_code);
			if (rows.length === 1) {
				const row = rows[0];
				const factor = flt(details.conversion_factors[row.uom]);
				if (factor <= 0) frappe.throw(__("UOM {0} is not configured for Item {1}.", [row.uom, item_code]));
				await frappe.model.set_value(row.doctype, row.name, "qty", stock_qty / factor);
			} else {
				const entered = rows.reduce((sum, row) => sum + flt(row.qty) * flt(details.conversion_factors[row.uom]), 0);
				if (Math.abs(entered - stock_qty) > 0.000001) {
					frappe.msgprint(__("Item {0}: quantities across all rows must equal {1} {2} from package scans.", [item_code, stock_qty, details.stock_uom]));
				}
			}
		}
	} finally {
		frm.package_barcode_enforcing_qty = false;
	}
};
