const standard_sales_order_listview_settings = frappe.listview_settings["Sales Order"] || {};

frappe.listview_settings["Sales Order"] = {
	...standard_sales_order_listview_settings,
	onload(listview) {
		standard_sales_order_listview_settings.onload?.(listview);
		srv_erp.list_view.setup_tree_group_filters(listview, [
			{ fieldname: "customer_group" },
		]);

		listview.page.add_actions_menu_item(__("Print Order Slip Ledger"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) {
				frappe.msgprint(__("Select at least one Sales Order to print."));
				return;
			}

			const print_window = window.open("", "_blank");
			if (!print_window) {
				frappe.msgprint(__("Please allow pop-ups to print the Order Slip Ledger."));
				return;
			}

			print_window.document.write(
				`<!doctype html><html><body style="font-family:sans-serif;padding:24px">${__(
					"Preparing Order Slip Ledger..."
				)}</body></html>`
			);

			frappe
				.call({
					method: "srv_erp.selling.order_slip.get_order_slip_ledger_html",
					args: { names },
				})
				.then((response) => {
					print_window.document.open();
					print_window.document.write(response.message);
					print_window.document.close();
				})
				.catch(() => print_window.close());
		});
	},
};
