const standard_sales_order_listview_settings = frappe.listview_settings["Sales Order"] || {};

function setup_live_customer_group_filter(listview) {
	const original_get_filters = listview.get_filters_for_args.bind(listview);
	const original_refresh = listview.refresh.bind(listview);
	let resolved_filter = null;

	const get_group_filter = () =>
		listview.filter_area
			?.get()
			.map((filter) => filter.slice(0, 4))
			.find(
				(filter) =>
					filter[0] === "Sales Order" &&
					filter[1] === "customer_group" &&
					filter[2] === "descendants of (inclusive)"
			);

	listview.get_filters_for_args = function () {
		const filters = original_get_filters();
		if (!resolved_filter) {
			return filters;
		}

		return filters.map((filter) => {
			if (
				filter[0] === "Sales Order" &&
				filter[1] === "customer_group" &&
				filter[2] === "descendants of (inclusive)" &&
				filter[3] === resolved_filter.customer_group
			) {
				return ["Sales Order", "customer", "in", resolved_filter.customers.length
					? resolved_filter.customers
					: [""]];
			}
			return filter;
		});
	};

	listview.refresh = async function (...args) {
		const group_filter = get_group_filter();
		resolved_filter = null;

		if (group_filter?.[3]) {
			const response = await frappe.call({
				method: "srv_erp.selling.sales_order_list.get_customers_in_group",
				args: { customer_group: group_filter[3] },
			});
			resolved_filter = {
				customer_group: group_filter[3],
				customers: response.message || [],
			};
		}

		return original_refresh(...args);
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
