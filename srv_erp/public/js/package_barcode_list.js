frappe.listview_settings["Package Barcode"] = {
	onload(listview) {
		listview.page.add_actions_menu_item(__("Download Selected Excel"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) {
				frappe.msgprint(__("Select at least one Package Barcode."));
				return;
			}

			const url =
				"/api/method/srv_erp.package_barcode.api.download_package_barcodes?names=" +
				encodeURIComponent(JSON.stringify(names));
			window.open(url, "_blank");
		});
	},
};
