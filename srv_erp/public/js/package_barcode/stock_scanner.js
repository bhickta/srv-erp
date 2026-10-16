srv_erp.package_barcode.PackageBarcodeScanner = class PackageBarcodeScanner extends erpnext.utils.BarcodeScanner {
	constructor(opts) {
		super({
			...opts,
			scan_api: "srv_erp.package_barcode.api.scan_package_barcode",
		});
	}

	process_scan() {
		if (this.frm.doctype !== "Delivery Note" || this.frm.doc.is_return) return this.process_single_scan();
		// Keep target selection and increments ordered even when a scanner sends rapid input.
		const input = this.scan_barcode_field.value;
		this.scan_barcode_field.set_value("");
		if (!input) return Promise.resolve();
		this.pending_scan = (this.pending_scan || Promise.resolve()).catch(() => {}).then(() => {
			this.scan_barcode_field.value = input;
			return this.process_single_scan();
		});
		return this.pending_scan;
	}

	process_single_scan() {
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
					this.stock_reconciliation_package_uom = data.uom;
					this.frm.package_barcode_recalculating_uom = true;
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
						this.stock_reconciliation_package_uom = null;
						this.frm.package_barcode_recalculating_uom = false;
						this.play_fail_sound();
						reject();
					});
			}).catch(reject);
		});
	}

	scan_api_call(input, callback) {
		return frappe.call({
			method: this.scan_api,
			args: { search_value: input, ctx: { set_warehouse: this.frm.doc.set_warehouse, company: this.frm.doc.company } },
		}).then(callback);
	}

	update_table(data) {
		if (this.frm.doctype !== "Delivery Note" || this.frm.doc.is_return) return super.update_table(data);
		return this.update_delivery_note_table(data);
	}

	choose_delivery_target(options, label, confirm = false) {
		if (options.length === 1 && !confirm) return Promise.resolve(options[0].value);
		return new Promise((resolve, reject) => {
			let chosen = false;
			const dialog = new frappe.ui.Dialog({
				title: label,
				fields: [{ fieldname: "target", fieldtype: "Select", label, reqd: 1,
					options: options.map((option) => option.label) }],
				primary_action_label: __("Select"),
				primary_action(values) {
					chosen = true;
					resolve(options.find((option) => option.label === values.target).value);
					dialog.hide();
				},
			});
			dialog.onhide = () => { if (!chosen) reject(new Error(__("Scan cancelled"))); };
			dialog.show();
		});
	}

	async update_delivery_note_table(data) {
		if (!this.frm.doc.customer || !this.frm.doc.company) {
			frappe.throw(__("Select a customer and company before scanning."));
		}
		const details = await srv_erp.package_barcode.get_item_uom_details(data.item_code);
		const scan_uom = data.uom || details.stock_uom;
		const scan_factor = flt(details.conversion_factors[scan_uom]);
		if (scan_factor <= 0) frappe.throw(__("UOM {0} is not configured for Item {1}.", [scan_uom, data.item_code]));
		const warehouse = this.frm.doc.last_scanned_warehouse || data.default_warehouse || this.frm.doc.set_warehouse;
		const added_qty = Number(data.qty ?? 1);
		if (!Number.isInteger(added_qty) || added_qty <= 0) {
			frappe.throw(__("Scanned quantity must be a positive whole number in {0}.", [scan_uom]));
		}
		const candidates = (this.frm.doc.items || []).filter((row) =>
			row.item_code === data.item_code && (!warehouse || !row.warehouse || row.warehouse === warehouse) &&
			(!row.batch_no || row.batch_no === data.batch_no) && !row.si_detail
		);
		const exact = candidates.filter((row) => row.uom === scan_uom);
		const linked = candidates.filter((row) => row.against_sales_order && row.so_detail);
		let reference;
		if (linked.length) {
			const preferred = exact.filter((row) => row.against_sales_order && row.so_detail);
			const choices = [...new Map((preferred.length ? preferred : linked).map((row) => [row.so_detail, row])).values()];
			reference = await this.choose_delivery_target(choices.map((row) => ({ value: row,
				label: __("{0}, Delivery Row {1}: {2} ({3})", [row.against_sales_order, row.idx, row.item_code, row.uom]) })), __("Select Sales Order Item"));
		} else {
			const response = await frappe.call({ method: "srv_erp.selling.delivery_note.get_delivery_scan_sales_order_items",
				args: { customer: this.frm.doc.customer, company: this.frm.doc.company, item_code: data.item_code } });
			const options = response.message || [];
			const choices = [...options].sort((left, right) => Number(!!left.is_substitution) - Number(!!right.is_substitution));
			if (choices.length) reference = await this.choose_delivery_target(choices.map((line) => ({ value: line,
				label: __("{0}, Row {1}: {2} ({3} {4} pending)", [line.against_sales_order, line.idx, line.item_code || data.item_code, line.pending_stock_qty, line.stock_uom || scan_uom]) })),
				choices.some((line) => line.is_substitution) ? __("Select Ordered Variant to Fulfill") : __("Select Sales Order Item"),
				choices.some((line) => line.is_substitution));
		}
		const targets = exact.filter((row) => !row.so_detail || row.so_detail === reference?.so_detail);
		let row;
		if (targets.length) row = await this.choose_delivery_target(targets.map((row) => ({ value: row,
			label: `${row.idx}: ${row.item_code} (${row.uom})` })), __("Select Item Row"));
		const is_new = !row;
		const kept_uom = scan_uom;
		const factor = scan_factor;
		const previous_qty = flt(row?.qty);
		if (row && this.is_duplicate_serial_no(row, data.serial_no)) throw new Error(__("Serial number already scanned"));
		if (!row) {
			if (this.dont_allow_new_row) frappe.throw(__("Cannot add another item row."));
			row = (this.frm.doc.items || []).find((row) => !row.item_code) ||
				frappe.model.add_child(this.frm.doc, this.frm.fields_dict.items.grid.doctype, "items");
		}
		this.delivery_scan_target = row;
		this.frm.package_barcode_delivery_scanning = true;
		try {
			this.set_selector_trigger_flag(data);
			if (reference) await frappe.model.set_value(row.doctype, row.name, {
				against_sales_order: reference.against_sales_order, so_detail: reference.so_detail,
			});
			if (is_new) {
				await frappe.model.set_value(row.doctype, row.name, "item_code", data.item_code);
				await frappe.model.set_value(row.doctype, row.name, "uom", kept_uom);
			}
			if (!row.warehouse && (warehouse || reference?.warehouse)) {
				await frappe.model.set_value(row.doctype, row.name, "warehouse", warehouse || reference.warehouse);
			}
			await frappe.model.set_value(row.doctype, row.name, "conversion_factor", factor);
			await frappe.model.set_value(row.doctype, row.name, "qty", previous_qty + added_qty);
			await this.set_serial_no(row, data.serial_no);
			await this.set_batch_no(row, data.batch_no);
			await this.set_barcode(row, data.barcode);
			this.show_scan_message(row.idx, !is_new, added_qty);
			this.frm.dirty();
			this.clean_up();
			return row;
		} finally {
			this.delivery_scan_target = null;
			this.frm.package_barcode_delivery_scanning = false;
			this.revert_selector_flag();
		}
	}

	is_duplicate_package_barcode(package_barcode) {
		return (this.frm.doc.package_barcodes || []).some((row) => {
			return row.package_barcode === package_barcode;
		});
	}

	get_row_to_modify_on_scan(item_code, batch_no, uom, barcode, default_warehouse) {
		if (this.frm.doctype === "Delivery Note" && !this.frm.doc.is_return) {
			if (this.delivery_scan_target) return this.delivery_scan_target;
			const warehouse = this.frm.doc.last_scanned_warehouse || default_warehouse || this.frm.doc.set_warehouse;
			const rows = (this.frm.doc.items || []).filter((row) => row.item_code === item_code &&
				(!warehouse || !row.warehouse || row.warehouse === warehouse) &&
				(!row.batch_no || row.batch_no === batch_no) && !row.si_detail);
			return rows.find((row) => row.uom === uom) ||
				(this.frm.doc.items || []).find((row) => !row.item_code);
		}
		if (this.frm.doctype !== "Stock Reconciliation" || !this.stock_reconciliation_package_uom) {
			return super.get_row_to_modify_on_scan(item_code, batch_no, uom, barcode, default_warehouse);
		}

		const items_table = this.frm.doc[this.items_table_name] || [];
		const target_warehouse = this.frm.doc.last_scanned_warehouse || default_warehouse || this.frm.doc.set_warehouse;
		const same_item_warehouse_row = items_table.find((row) => {
			const warehouse_matches = !target_warehouse || !row.warehouse || row.warehouse === target_warehouse;
			return row.item_code === item_code && warehouse_matches;
		});
		if (same_item_warehouse_row) {
			this.stock_reconciliation_scan_row_state = {
				name: same_item_warehouse_row.name,
				qty: flt(same_item_warehouse_row.qty),
				package_qty: flt(same_item_warehouse_row.package_qty),
				package_uom: same_item_warehouse_row.package_uom,
				package_conversion_factor: flt(same_item_warehouse_row.package_conversion_factor),
			};
			return same_item_warehouse_row;
		}

		const empty_row = items_table.find((row) => !row.item_code);
		this.stock_reconciliation_scan_row_state = empty_row
			? {
				name: empty_row.name,
				qty: 0,
				package_qty: 0,
				package_uom: null,
				package_conversion_factor: 0,
			}
			: null;
		return empty_row;
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
