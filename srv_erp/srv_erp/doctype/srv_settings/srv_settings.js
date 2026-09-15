frappe.ui.form.on("SRV Settings", {
	setup(frm) {
		frm.set_query("stock_entry_price_list", () => ({
			filters: { enabled: 1 },
		}));
	},
});
