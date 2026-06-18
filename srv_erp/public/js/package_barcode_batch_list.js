frappe.listview_settings["Package Barcode Batch"] = {
	onload(listview) {
		listview.page.add_actions_menu_item(__("Download Batch Excel"), () => {
			const batches = listview.get_checked_items(true);
			if (!batches.length) {
				frappe.msgprint(__("Select at least one Package Barcode Batch."));
				return;
			}

			const url =
				"/api/method/srv_erp.package_barcode.api.download_package_barcode_batches?batches=" +
				encodeURIComponent(JSON.stringify(batches));
			window.open(url, "_blank");
		});
	},
};
