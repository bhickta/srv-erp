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
	if (frm.doctype === "Stock Reconciliation") {
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
