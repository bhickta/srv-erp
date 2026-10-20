frappe.listview_settings["SRV Production Assignment"] = {
	filters: [
		[
			"status",
			"not in",
			frappe.meta
				.get_docfield("SRV Production Assignment", "status")
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
	add_fields: ["status", "planned_date", "remaining_qty"],
	get_indicator(doc) {
		if (
			doc.status !== "Completed" &&
			doc.status !== "Cancelled" &&
			doc.planned_date < frappe.datetime.get_today()
		) {
			return [
				__("Overdue"),
				"red",
				"planned_date,<,Today|status,not in,Completed,Cancelled",
			];
		}
		return [
			__(doc.status),
			{ Completed: "green", "In Progress": "orange", Cancelled: "gray" }[doc.status] ||
				"blue",
			`status,=,${doc.status}`,
		];
	},
};
