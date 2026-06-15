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
					this.clean_up();
					this.play_fail_sound();
					reject();
					return;
				}

				this.update_table(data)
					.then((row) => {
						if (data.package_barcode) {
							this.add_package_barcode_scan(data);
						}
						this.play_success_sound();
						resolve(row);
					})
					.catch(() => {
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
	}
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
};

frappe.ui.form.on("Stock Entry", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});

frappe.ui.form.on("Delivery Note", {
	setup: srv_erp.package_barcode.setup_stock_scanner,
	refresh: srv_erp.package_barcode.setup_stock_scanner,
});
