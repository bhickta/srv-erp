const standard_sales_order_listview_settings =
	frappe.listview_settings["Sales Order"] || {};

const CUSTOM_DELIVERY_STATUS = "Partly or Not Delivered";
const CUSTOM_DELIVERY_STATUS_VALUE = "__partly_or_not_delivered__";


function setup_live_customer_group_filter(listview) {
	listview.method = "srv_erp.selling.sales_order_list.get";

	listview.get_count_str = async function () {
		const current_count = this.data.length;
		const count_without_children = this.data.uniqBy((doc) => doc.name).length;

		const total_count = await frappe.xcall(
			"srv_erp.selling.sales_order_list.get_count",
			{
				doctype: this.doctype,
				filters: this.get_filters_for_args(),
				fields: [],
				distinct: count_without_children !== current_count,
				limit: this.count_upper_bound,
			}
		);

		this.total_count = total_count || current_count;

		this.count_without_children =
			count_without_children !== current_count
				? count_without_children
				: undefined;

		const total =
			this.total_count === this.count_upper_bound
				? `${format_number(this.total_count - 1, null, 0)}+`
				: format_number(this.total_count, null, 0);

		let count = __("{0} of {1}", [
			format_number(current_count, null, 0),
			total,
		]);

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


function setup_custom_delivery_status_filter(listview) {
	const delivery_status_field =
		listview.page.fields_dict?.delivery_status;

	if (!delivery_status_field) {
		console.warn(
			"[Sales Order] Delivery Status standard filter was not found."
		);

		return;
	}


	let options = delivery_status_field.df.options || "";

	if (typeof options === "string") {
		options = options
			.split("\n")
			.filter((option) => option.trim());
	} else {
		options = [...options];
	}

	if (!options.includes(CUSTOM_DELIVERY_STATUS_VALUE)) {
		options.push({
			label: CUSTOM_DELIVERY_STATUS,
			value: CUSTOM_DELIVERY_STATUS_VALUE,
		});
	}

	delivery_status_field.df.options = options;
	delivery_status_field.set_options();


	if (listview.__custom_delivery_status_filter_setup) {
		return;
	}

	const original_get_filters_for_args =
		listview.get_filters_for_args.bind(listview);

	listview.get_filters_for_args = function () {
		const filters = original_get_filters_for_args();

		return filters.flatMap((filter) => {
			const [doctype, fieldname, condition, value] = filter;

			if (
				doctype === "Sales Order" &&
				fieldname === "delivery_status" &&
				condition === "=" &&
				value === CUSTOM_DELIVERY_STATUS_VALUE
			) {
				return [
					[
						"Sales Order",
						"delivery_status",
						"in",
						["Not Delivered", "Partly Delivered"],
					],
				];
			}

			return [filter];
		});
	};

	listview.__custom_delivery_status_filter_setup = true;
}


frappe.listview_settings["Sales Order"] = {
	...standard_sales_order_listview_settings,
	// filters: [
	// 	[
	// 		"delivery_status",
	// 		"=",
	// 		CUSTOM_DELIVERY_STATUS_VALUE,
	// 	],
	// ],	
	onload(listview) {
		standard_sales_order_listview_settings.onload?.(listview);
		srv_erp.list_view.setup_tree_group_filters(listview, [
			{ fieldname: "customer_group" },
		]);

		setup_live_customer_group_filter(listview);
		setup_custom_delivery_status_filter(listview);


		listview.page.add_actions_menu_item(
			__("Print Order Slip Ledger"),
			() => {
				const names = listview.get_checked_items(true);

				if (!names.length) {
					frappe.msgprint(
						__("Select at least one Sales Order to print.")
					);

					return;
				}

				const print_window = window.open("", "_blank");

				if (!print_window) {
					frappe.msgprint(
						__(
							"Please allow pop-ups to print the Order Slip Ledger."
						)
					);

					return;
				}

				print_window.document.write(
					`<!doctype html>
					<html>
						<body style="font-family:sans-serif;padding:24px">
							${__("Preparing Order Slip Ledger...")}
						</body>
					</html>`
				);

				frappe
					.call({
						method:
							"srv_erp.selling.order_slip.get_order_slip_ledger_html",
						args: { names },
					})
					.then((response) => {
						print_window.document.open();
						print_window.document.write(response.message);
						print_window.document.close();
					})
					.catch(() => print_window.close());
			},

		);

		listview.page.add_action_item(
			__("Print Pending Order Slip Ledger"),
			() => {
				const names = listview.get_checked_items(true);

				if (!names.length) {
					frappe.msgprint(
						__("Select at least one Sales Order to print.")
					);
					return;
				}

				const print_window = window.open("", "_blank");

				if (!print_window) {
					frappe.msgprint(
						__(
							"Please allow pop-ups to print the Pending Order Slip Ledger."
						)
					);
					return;
				}

				print_window.document.write(`
					<!doctype html>
					<html>
						<body style="font-family:sans-serif;padding:24px">
							${__("Preparing Pending Order Slip Ledger...")}
						</body>
					</html>
				`);

				frappe
					.call({
						method:
							"srv_erp.selling.order_slip.get_pending_order_slip_ledger_html",
						args: { names },
					})
					.then((response) => {
						print_window.document.open();
						print_window.document.write(response.message);
						print_window.document.close();
					})
					.catch(() => print_window.close());
			}
		);

		listview.page.add_action_item(
			__("Print Required Stock"),
			() => {
				const names = listview.get_checked_items(true);

				if (!names.length) {
					frappe.msgprint(
						__("Select at least one Sales Order to print.")
					);
					return;
				}

				const print_window = window.open("", "_blank");

				if (!print_window) {
					frappe.msgprint(
						__("Please allow pop-ups to print the Required Stock.")
					);
					return;
				}

				print_window.document.write(`
					<!doctype html>
					<html>
						<body style="font-family:sans-serif;padding:24px">
							${__("Preparing Required Stock...")}
						</body>
					</html>
				`);

				frappe
					.call({
						method:
							"srv_erp.selling.order_slip.get_required_stock_html",
						args: { names },
					})
					.then((response) => {
						print_window.document.open();
						print_window.document.write(response.message);
						print_window.document.close();
					})
					.catch(() => {
						print_window.close();
					});
			}
		);
	},
};