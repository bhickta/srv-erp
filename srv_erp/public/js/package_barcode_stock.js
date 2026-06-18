frappe.provide("srv_erp.package_barcode");

srv_erp.package_barcode.PackageBarcodeScanner = class PackageBarcodeScanner extends erpnext.utils.BarcodeScanner {
	constructor(opts) {
		super({
			...opts,
			scan_api: "srv_erp.package_barcode.api.scan_package_barcode",
		});
	}

	process_scan() {
		return new Promise((resolve, reject) => {
			const input = this.scan_barcode_field.value;
			this.scan_barcode_field.set_value("");
			if (!input) {
				return;
			}

			this.scan_api_call(input, (r) => {
				const data = r && r.message;
				if (
					!data ||
					Object.keys(data).length === 0 ||
					(data.warehouse && !this.has_last_scanned_warehouse)
				) {
					this.show_alert(__("Cannot find Item with this Barcode"), "red");
					srv_erp.package_barcode.record_blocked_scan(this.frm, input);
					this.clean_up();
					this.play_fail_sound();
					reject();
					return;
				}

				if (data.warehouse) {
					this.handle_warehouse_scan(data);
					this.play_success_sound();
					resolve();
					return;
				}

				if (data.package_barcode && this.is_duplicate_package_barcode(data.package_barcode)) {
					this.show_alert(__("Package Barcode {0} is already scanned in this document", [data.barcode]), "orange");
					srv_erp.package_barcode.record_blocked_scan(this.frm, data.barcode);
					this.clean_up();
					this.play_fail_sound();
					reject();
					return;
				}

				const row_data = data.package_barcode ? { ...data, barcode: null } : data;

				this.update_table(row_data)
					.then((row) => {
						if (data.package_barcode) {
							this.add_package_barcode_scan(data);
							srv_erp.package_barcode.record_successful_scan(this.frm, data.barcode);
						}
						this.play_success_sound();
						resolve(row);
					})
					.catch(() => {
						if (data.package_barcode) {
							srv_erp.package_barcode.record_blocked_scan(this.frm, data.barcode);
						}
						this.play_fail_sound();
						reject();
					});
			});
		});
	}

	is_duplicate_package_barcode(package_barcode) {
		return (this.frm.doc.package_barcodes || []).some((row) => {
			return row.package_barcode === package_barcode;
		});
	}

	add_package_barcode_scan(data) {
		if (!frappe.meta.has_field(this.frm.doctype, "package_barcodes")) {
			return;
		}

		const row = frappe.model.add_child(this.frm.doc, "Package Barcode Scan", "package_barcodes");
		row.package_barcode = data.package_barcode;
		row.barcode = data.barcode;
		row.item_code = data.item_code;
		row.uom = data.uom;
		refresh_field("package_barcodes");
		srv_erp.package_barcode.render_scan_review(this.frm);
	}
};

srv_erp.package_barcode.get_scan_stats = function (frm) {
	if (!frm.package_barcode_scan_stats) {
		frm.package_barcode_scan_stats = {
			blocked_scans: 0,
			last_scanned: null,
		};
	}

	return frm.package_barcode_scan_stats;
};

srv_erp.package_barcode.record_successful_scan = function (frm, barcode) {
	const stats = srv_erp.package_barcode.get_scan_stats(frm);
	stats.last_scanned = barcode;
	srv_erp.package_barcode.render_scan_review(frm);
};

srv_erp.package_barcode.record_blocked_scan = function (frm, barcode) {
	const stats = srv_erp.package_barcode.get_scan_stats(frm);
	stats.blocked_scans += 1;
	stats.last_scanned = barcode;
	srv_erp.package_barcode.render_scan_review(frm);
};

srv_erp.package_barcode.render_scan_review = function (frm) {
	if (!frm.fields_dict.scan_barcode || !frappe.meta.has_field(frm.doctype, "package_barcodes")) {
		return;
	}

	const stats = srv_erp.package_barcode.get_scan_stats(frm);
	const rows = frm.doc.package_barcodes || [];
	const last_row = rows.length ? rows[rows.length - 1] : null;
	const last_scanned = stats.last_scanned || last_row?.barcode || "-";
	const total_scanned = rows.length;
	const total_qty = rows.length;

	const html = `
		<div class="srv-package-barcode-review">
			<div class="srv-package-barcode-review__item">
				<div class="text-muted small">${__("Packages Scanned")}</div>
				<div class="h5 mb-0">${total_scanned}</div>
			</div>
			<div class="srv-package-barcode-review__item">
				<div class="text-muted small">${__("Qty Added")}</div>
				<div class="h5 mb-0">${total_qty}</div>
			</div>
			<div class="srv-package-barcode-review__item">
				<div class="text-muted small">${__("Blocked")}</div>
				<div class="h5 mb-0">${stats.blocked_scans}</div>
			</div>
			<div class="srv-package-barcode-review__item srv-package-barcode-review__last">
				<div class="text-muted small">${__("Last Scan")}</div>
				<div class="text-truncate">${frappe.utils.escape_html(last_scanned)}</div>
			</div>
		</div>
	`;

	frm.fields_dict.scan_barcode.$wrapper.next(".srv-package-barcode-review").remove();
	frm.fields_dict.scan_barcode.$wrapper.after(html);
};

srv_erp.package_barcode.setup_stock_scanner = function (frm) {
	if (!frm.cscript || !(erpnext && erpnext.utils && erpnext.utils.BarcodeScanner)) {
		return;
	}

	const opts = { frm };
	if (frm.doc.doctype === "Stock Entry") {
		opts.warehouse_field = (doc) => {
			return doc.purpose === "Material Receipt" ? "t_warehouse" : "s_warehouse";
		};
	}

	frm.cscript.barcode_scanner = new srv_erp.package_barcode.PackageBarcodeScanner(opts);
	srv_erp.package_barcode.render_scan_review(frm);
};

frappe.dom.set_style(`
	.srv-package-barcode-review {
		align-items: stretch;
		background: var(--control-bg);
		border: 1px solid var(--border-color);
		border-radius: 8px;
		display: grid;
		gap: 0;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		margin: -2px 0 12px;
		overflow: hidden;
	}
	.srv-package-barcode-review__item {
		border-right: 1px solid var(--border-color);
		padding: 8px 10px;
		min-width: 0;
	}
	.srv-package-barcode-review__item:last-child {
		border-right: 0;
	}
	.srv-package-barcode-review__last {
		min-width: 150px;
	}
	@media (max-width: 767px) {
		.srv-package-barcode-review {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.srv-package-barcode-review__item:nth-child(2) {
			border-right: 0;
		}
		.srv-package-barcode-review__item:nth-child(-n + 2) {
			border-bottom: 1px solid var(--border-color);
		}
	}
`);

frappe.ui.form.on("Stock Entry", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});

frappe.ui.form.on("Delivery Note", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});
