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
				if (data.package_barcode && this.frm.doctype === "Stock Reconciliation") {
					row_data.uom = null;
				}

				this.update_table(row_data)
					.then((row) => {
						if (data.package_barcode) {
							return Promise.resolve(
								srv_erp.package_barcode.apply_stock_reconciliation_package_uom(this.frm, row, data)
							).then(() => {
								this.add_package_barcode_scan(data);
								srv_erp.package_barcode.record_successful_scan(this.frm, data.barcode);
							});
						}
						return null;
					})
					.then(() => {
						this.play_success_sound();
						resolve();
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
		srv_erp.package_barcode.refresh_barcode_only_items(this.frm);
		srv_erp.package_barcode.render_scan_review(this.frm);
	}
};
