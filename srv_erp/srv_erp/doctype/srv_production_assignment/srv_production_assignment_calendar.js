frappe.views.calendar["SRV Production Assignment"] = {
	field_map: {
		id: "name",
		start: "planned_date",
		end: "planned_date",
		title: "calendar_title",
		allDay: 1,
		editable: "calendar_editable",
		convertToUserTz: "convert_to_user_tz",
	},
	get_events_method: "srv_erp.production.service.get_events",
	options: { editable: false, selectable: false, droppable: false },
	get_css_class(data) {
		return (
			{ Completed: "success", "In Progress": "warning", Cancelled: "danger" }[data.status] ||
			"default"
		);
	},
};
