const standard_delivery_note_listview_settings =
	frappe.listview_settings["Delivery Note"] || {};

frappe.listview_settings["Delivery Note"] = {
	...standard_delivery_note_listview_settings,
	onload(listview) {
		standard_delivery_note_listview_settings.onload?.(listview);
		srv_erp.list_view.setup_tree_group_filters(listview, [
			{ fieldname: "customer_group" },
		]);

		listview.page.add_actions_menu_item(
			__("Print Delivery Note Ledger"),
			() => {
				print_delivery_notes(
					listview,
					"srv_erp.selling.order_slip.get_delivery_note_ledger_html",
					__("Delivery Note Ledger")
				);
			}
		);

		listview.page.add_actions_menu_item(
			__("Print Delivery Note Valuation"),
			() => {
				print_delivery_notes(
					listview,
					"srv_erp.selling.order_slip.get_delivery_note_valuation_html",
					__("Delivery Note Valuation")
				);
			}
		);
	},
};

function print_delivery_notes(listview, method, title) {
	const names = listview.get_checked_items(true);

	if (!names.length) {
		frappe.msgprint(__("Select at least one Delivery Note to print."));
		return;
	}

	const print_window = window.open("", "_blank");

	if (!print_window) {
		frappe.msgprint(
			__("Please allow pop-ups to print the {0}.", [title])
		);
		return;
	}

	print_window.document.write(`
		<!doctype html>
		<html>
			<body style="font-family:sans-serif;padding:24px">
				${__("Preparing {0}...", [title])}
			</body>
		</html>
	`);

	frappe
		.call({ method, args: { names } })
		.then((response) => {
			print_window.document.open();
			print_window.document.write(response.message);
			print_window.document.close();
		})
		.catch((error) => {
			print_window.close();
			frappe.msgprint(
				error.message ||
					__("Unable to prepare the {0}.", [title])
			);
		});
}
