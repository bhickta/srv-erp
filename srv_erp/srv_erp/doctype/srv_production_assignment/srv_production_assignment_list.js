frappe.listview_settings["SRV Production Assignment"] = {
	filters: [
		["planned_date", "timespan", "today"],
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
		// Fill missing defaults independently for existing saved views. Explicit
		// date/status filters and filters removed during this visit stay editable.
		const filters = listview.filter_area.get();
		const defaults = frappe.listview_settings[listview.doctype].filters.filter(
			([fieldname]) =>
				!filters.some(
					(filter) =>
						filter[1] === fieldname ||
						(fieldname === "status" && filter[1] === "docstatus"),
				),
		);
		if (defaults.length) {
			return listview.filter_area.add(
				defaults.map((filter) => [listview.doctype, ...filter]),
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
