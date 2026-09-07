const standard_sales_order_listview_settings = frappe.listview_settings["Sales Order"] || {};

function setup_live_customer_group_filter(listview) {
	listview.method = "srv_erp.selling.sales_order_list.get";
	listview.get_count_str = async function () {
		const current_count = this.data.length;
		const count_without_children = this.data.uniqBy((doc) => doc.name).length;
		const total_count = await frappe.xcall("srv_erp.selling.sales_order_list.get_count", {
			doctype: this.doctype,
			filters: this.get_filters_for_args(),
			fields: [],
			distinct: count_without_children !== current_count,
			limit: this.count_upper_bound,
		});

		this.total_count = total_count || current_count;
		this.count_without_children =
			count_without_children !== current_count ? count_without_children : undefined;

		const total =
			this.total_count === this.count_upper_bound
				? `${format_number(this.total_count - 1, null, 0)}+`
				: format_number(this.total_count, null, 0);
		let count = __("{0} of {1}", [format_number(current_count, null, 0), total]);
		if (this.count_without_children) {
			count = __("{0} of {1} ({2} rows with children)", [
				this.count_without_children,
				total,
				current_count,
			]);
		}
		return count;
	};
}

frappe.listview_settings["Sales Order"] = {
	...standard_sales_order_listview_settings,
	onload(listview) {
		standard_sales_order_listview_settings.onload?.(listview);
		srv_erp.list_view.setup_tree_group_filters(listview, [
			{ fieldname: "customer_group" },
		]);
		setup_live_customer_group_filter(listview);

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
