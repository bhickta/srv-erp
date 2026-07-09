frappe.query_reports["Variant Coverage"] = {
	filters: [
		{
			fieldname: "item_template",
			label: __("Item Template"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({
				filters: {
					has_variants: 1,
					variant_based_on: "Item Attribute",
				},
			}),
		},
		{
			fieldname: "variant_attribute",
			label: __("Variant Attribute"),
			fieldtype: "Link",
			options: "Item Attribute",
			default: "Brand",
		},
		{
			fieldname: "attribute_value",
			label: __("Attribute Value"),
			fieldtype: "Data",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["All", "Created", "Missing"],
			default: "All",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "view_by",
			label: __("View By"),
			fieldtype: "Select",
			options: ["Template", "Attribute Value"],
			default: "Template",
		},
		{
			fieldname: "include_disabled_variants",
			label: __("Include Disabled Variants"),
			fieldtype: "Check",
			default: 0,
		},
	],

	onload(report) {
		if (!frappe.model.can_create("Item")) {
			return;
		}

		report.page.add_inner_button(__("Create Missing Variants"), () => {
			const filters = report.get_values();

			frappe.confirm(
				__(
					"Create all missing variants from the current filters? Please review the report before continuing."
				),
				() => {
					frappe.call({
						method: "srv_erp.srv_erp.report.variant_coverage.variant_coverage.create_missing_variants",
						args: { filters },
						freeze: true,
						freeze_message: __("Creating missing variants..."),
						callback(response) {
							const result = response.message || {};
							if (result.queued) {
								frappe.show_alert({
									message: __("{0} variants queued for creation", [result.queued]),
									indicator: "blue",
								});
							} else {
								frappe.show_alert({
									message: __("{0} variants created, {1} skipped", [
										result.created || 0,
										result.skipped || 0,
									]),
									indicator: "green",
								});
							}

							report.refresh();
						},
					});
				}
			);
		});
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname !== "status" || !data) {
			return value;
		}

		const indicator = data.status === "Created" ? "green" : "orange";
		return `<span class="indicator-pill ${indicator}">${value}</span>`;
	},
};
