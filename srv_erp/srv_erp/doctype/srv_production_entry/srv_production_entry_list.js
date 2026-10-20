frappe.listview_settings["SRV Production Entry"] = {
	filters: [
		[
			"status",
			"not in",
			frappe.meta
				.get_docfield("SRV Production Entry", "status")
				.options.split("\n")
				.filter((status) => ["Cancelled", "Rejected", "Disabled"].includes(status)),
		],
	],
	onload(listview) {
		// Apply the default to existing empty saved views too. Explicit history
		// filters and filters removed during this visit remain under user control.
		if (
			!listview.filter_area
				.get()
				.some((filter) => ["status", "docstatus"].includes(filter[1]))
		) {
			return listview.filter_area.add(
				frappe.listview_settings[listview.doctype].filters.map((filter) => [
					listview.doctype,
					...filter,
				]),
			);
		}
	},
};
