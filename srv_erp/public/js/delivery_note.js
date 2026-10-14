frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		const grid = frm.fields_dict.items.grid;
		grid.update_docfield_property("qty", "formatter", (value, df, options, row) => {
			const qty = frappe.format(value, { fieldtype: "Float", precision: df.precision });
			const stock = frappe.utils.escape_html(`${flt(row.stock_qty)} ${row.stock_uom || ""}`);
			return `${qty}<div class="text-muted small">${stock}</div>`;
		});
		for (const field of ["stock_qty", "stock_uom"]) {
			grid.update_docfield_property(field, "hidden", 0);
			grid.update_docfield_property(field, "in_list_view", 1);
			grid.update_docfield_property(field, "read_only", 1);
		}
		frm.add_custom_button(__("Enter Quantity in Another UOM"), () => {
			const rows = (frm.doc.items || []).filter((row) => row.item_code);
			if (!rows.length || frm.doc.docstatus || frm.doc.is_return) return;
			frappe.prompt([
				{ fieldname: "row", fieldtype: "Select", label: __("Item Row"), reqd: 1,
					options: rows.map((row) => `${row.idx}: ${row.item_code} (${row.uom})`) },
				{ fieldname: "uom", fieldtype: "Link", options: "UOM", label: __("Entered UOM"), reqd: 1 },
				{ fieldname: "qty", fieldtype: "Float", label: __("Delivered Quantity"), reqd: 1 },
			], async (values) => {
				const row = rows.find((row) => row.idx === Number(values.row.split(":")[0]));
				const details = await srv_erp.package_barcode.get_item_uom_details(row.item_code);
				const entered = flt(details.conversion_factors[values.uom]);
				const kept = flt(details.conversion_factors[row.uom]);
				if (entered <= 0 || kept <= 0) {
					frappe.throw(__("UOM is not configured for Item {0}.", [row.item_code]));
				}
				await frappe.model.set_value(row.doctype, row.name, "qty", flt(values.qty) * entered / kept);
			}, __("Enter Delivered Quantity"));
		});
	},
});
