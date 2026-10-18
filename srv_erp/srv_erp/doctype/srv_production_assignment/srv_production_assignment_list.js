frappe.listview_settings["SRV Production Assignment"] = {
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
