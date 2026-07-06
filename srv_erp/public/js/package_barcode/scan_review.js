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
