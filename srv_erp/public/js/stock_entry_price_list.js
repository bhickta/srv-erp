function set_stock_entry_price_list_rate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (
		!row?.item_code ||
		!row.stock_uom ||
		!row.transfer_qty ||
		!row.t_warehouse ||
		row.s_warehouse ||
		row.allow_zero_valuation_rate ||
		row.set_basic_rate_manually
	) {
		return;
	}

	return frappe
		.call({
			method: "srv_erp.stock.stock_entry.get_configured_stock_entry_rate",
			args: {
				item_code: row.item_code,
				stock_uom: row.stock_uom,
				qty: row.transfer_qty,
				posting_date: frm.doc.posting_date,
				company: frm.doc.company,
				batch_no: row.batch_no,
			},
		})
		.then((response) => {
			const current_row = locals[cdt]?.[cdn];
			if (
				response.message?.rate != null &&
				current_row?.item_code === row.item_code &&
				flt(current_row.basic_rate) !== flt(response.message.rate)
			) {
				return frappe.model.set_value(cdt, cdn, "basic_rate", response.message.rate);
			}
		});
}

function refresh_stock_entry_price_list_rates(frm) {
	return Promise.all(
		(frm.doc.items || []).map((row) =>
			set_stock_entry_price_list_rate(frm, row.doctype, row.name)
		)
	);
}

frappe.ui.form.on("Stock Entry", {
	posting_date: refresh_stock_entry_price_list_rates,
	company: refresh_stock_entry_price_list_rates,
});

frappe.ui.form.on("Stock Entry Detail", {
	item_code: set_stock_entry_price_list_rate,
	qty: set_stock_entry_price_list_rate,
	conversion_factor: set_stock_entry_price_list_rate,
	t_warehouse: set_stock_entry_price_list_rate,
	batch_no: set_stock_entry_price_list_rate,
	allow_zero_valuation_rate: set_stock_entry_price_list_rate,
	set_basic_rate_manually: set_stock_entry_price_list_rate,
});
