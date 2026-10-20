frappe.listview_settings["SRV Production Schedule"] = {
	add_fields: ["status", "percent_completed", "remaining_items"],
	get_indicator(doc) {
		return [
			__(doc.status),
			{
				Draft: "gray",
				"To Produce": "blue",
				"Partly Produced": "orange",
				Completed: "green",
				Cancelled: "red",
			}[doc.status] || "gray",
			`status,=,${doc.status}`,
		];
	},
};
