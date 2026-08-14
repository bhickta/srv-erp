frappe.listview_settings["Dynamic Item Request"] = {
	add_fields: ["status", "request_type", "staged_item_code", "resolved_item"],
	get_indicator(doc) {
		const colours = {
			"Pending Approval": "orange",
			Approved: "green",
			Rejected: "red",
			Cancelled: "gray",
		};
		return [__(doc.status), colours[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
