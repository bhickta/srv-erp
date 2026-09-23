frappe.query_reports["Brand Variant Rule Conflicts"] = {
	filters: [
		{ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "Brand" },
		{
			fieldname: "template_item",
			label: __("Item Template"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_attribute",
			label: __("Item Attribute"),
			fieldtype: "Link",
			options: "Item Attribute",
		},
		{ fieldname: "conflict_type", label: __("Conflict Type"), fieldtype: "Data" },
		{ fieldname: "revision", label: __("Revision"), fieldtype: "Int" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOpen\nResolved",
			default: "Open",
		},
	],
};
