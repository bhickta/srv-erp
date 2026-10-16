frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		const grid = frm.fields_dict.items.grid;
		grid.update_docfield_property("qty", "formatter", (value, df, options, row) => {
			const qty = frm.doc.is_return ? frappe.format(value, { fieldtype: "Float", precision: df.precision }) : frappe.utils.escape_html(String(flt(value)));
			const stock = frappe.utils.escape_html(`${flt(row.stock_qty)} ${row.stock_uom || ""}`);
			return `${qty}<div class="text-muted small">${stock}</div>`;
		});
		if (!frm.delivery_qty_display) {
			frm.delivery_qty_display = { precision: grid.docfields.find((df) => df.fieldname === "qty")?.precision };
		}
		grid.update_docfield_property("qty", "precision", frm.doc.is_return ? frm.delivery_qty_display.precision : 0);
		for (const field of ["stock_qty", "stock_uom"]) {
			grid.update_docfield_property(field, "hidden", 0);
			grid.update_docfield_property(field, "in_list_view", 1);
			grid.update_docfield_property(field, "read_only", 1);
		}
	},
});
