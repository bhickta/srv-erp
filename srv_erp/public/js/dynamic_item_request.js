frappe.provide("srv_erp.dynamic_item");

srv_erp.dynamic_item.client_settings = {};

srv_erp.dynamic_item.get_client_settings = function (doctype) {
	if (!srv_erp.dynamic_item.client_settings[doctype]) {
		srv_erp.dynamic_item.client_settings[doctype] = frappe
			.call({
				method: "srv_erp.masters.dynamic_item.api.get_dynamic_item_client_settings",
				args: { document_type: doctype },
			})
			.then((response) => response.message || {});
	}
	return srv_erp.dynamic_item.client_settings[doctype];
};

srv_erp.dynamic_item.configure_form = function (frm) {
	if (!frm?.doctype) {
		return;
	}
	srv_erp.dynamic_item.get_client_settings(frm.doctype).then((settings) => {
		if (!settings.enabled) {
			return;
		}
		(settings.grids || []).forEach((config) => {
			const grid = frm.fields_dict[config.fieldname]?.grid;
			if (!grid || grid.__dynamic_item_request_button) {
				return;
			}
			grid.__dynamic_item_request_button = true;
			grid.add_custom_button(__("Resolve / Request Item"), () => {
				srv_erp.dynamic_item.open_template_dialog(frm, config);
			});
		});
	});
};

srv_erp.dynamic_item.configure_template_item = function (frm) {
	if (!frm.doc.has_variants || frm.doc.variant_based_on !== "Item Attribute") {
		return;
	}
	srv_erp.dynamic_item.get_client_settings("Item").then((settings) => {
		if (settings.approval_enforced || !settings.bulk_variant_creation_enabled) {
			frm.remove_custom_button(__("Single Variant"), __("Create"));
			frm.remove_custom_button(__("Multiple Variants"), __("Create"));
		}
		if (!settings.enabled) {
			return;
		}
		frm.add_custom_button(
			__("Request Variant"),
			() => srv_erp.dynamic_item.open_parameter_dialog(frm.doc.name, null, null),
			__("Create")
		);
	});
};

srv_erp.dynamic_item.open_template_dialog = function (frm, grid_config) {
	const dialog = new frappe.ui.Dialog({
		title: __("Resolve or Request Item"),
		fields: [
			{
				fieldname: "template_item",
				fieldtype: "Link",
				label: __("Item Template"),
				options: "Item",
				reqd: 1,
				get_query: () => ({
					filters: { has_variants: 1, variant_based_on: "Item Attribute", disabled: 0 },
				}),
			},
		],
		primary_action_label: __("Next"),
		primary_action(values) {
			dialog.hide();
			srv_erp.dynamic_item.open_parameter_dialog(values.template_item, frm, grid_config);
		},
	});
	dialog.show();
};

srv_erp.dynamic_item.open_parameter_dialog = function (template_item, frm, grid_config) {
	frappe.call({
		method: "srv_erp.masters.dynamic_item.api.get_dynamic_variant_options",
		args: {
			template_item,
			source_doctype: frm?.doctype,
			source_field: grid_config?.fieldname,
		},
		freeze: true,
		freeze_message: __("Loading variant parameters..."),
		callback(response) {
			const options = response.message;
			if (!options) return;
			srv_erp.dynamic_item.show_parameter_dialog(options, frm, grid_config);
		},
	});
};

srv_erp.dynamic_item.show_parameter_dialog = function (options, frm, grid_config) {
	const attribute_fields = [];
	const attribute_field_map = {};
	(options.attributes || []).forEach((attribute, index) => {
		const fieldname = `variant_attribute_${index}`;
		attribute_field_map[fieldname] = attribute.attribute;
		attribute_fields.push({
			fieldname,
			fieldtype: attribute.numeric_values ? "Float" : "Autocomplete",
			label: attribute.attribute,
			options: attribute.values || [],
			reqd: attribute.required ? 1 : 0,
			description: attribute.allow_new_values
				? __("Select an existing value or type a new categorical value.")
				: __("Select an existing value."),
		});
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Configure {0}", [options.template_item]),
		size: "large",
		fields: [
			{
				fieldname: "template_item",
				fieldtype: "Link",
				label: __("Item Template"),
				options: "Item",
				default: options.template_item,
				read_only: 1,
			},
			{ fieldtype: "Section Break", label: __("Variant Identity") },
			...attribute_fields,
			options.allow_dynamic_attributes
				? {
						fieldname: "additional_attributes",
						fieldtype: "Table",
						label: __("Additional Categorical Attributes"),
						cannot_add_rows: false,
						in_place_edit: true,
						fields: [
							{
								fieldname: "attribute",
								fieldtype: "Data",
								label: __("Attribute"),
								in_list_view: 1,
								reqd: 1,
							},
							{
								fieldname: "attribute_value",
								fieldtype: "Data",
								label: __("Value"),
								in_list_view: 1,
								reqd: 1,
							},
						],
				  }
				: null,
			{ fieldtype: "Section Break", label: __("Packaging UOMs") },
			{
				fieldname: "uoms",
				fieldtype: "Table",
				label: __("Packaging UOMs"),
				cannot_add_rows: false,
				in_place_edit: true,
				fields: [
					{
						fieldname: "uom",
						fieldtype: "Link",
						label: __("UOM"),
						options: "UOM",
						in_list_view: 1,
						reqd: 1,
					},
					{
						fieldname: "conversion_factor",
						fieldtype: "Float",
						label: __("Conversion Factor"),
						in_list_view: 1,
						reqd: 1,
					},
				],
			},
		].filter(Boolean),
		primary_action_label: __("Resolve / Request"),
		primary_action(values) {
			const attributes = {};
			Object.entries(attribute_field_map).forEach(([fieldname, attribute]) => {
				if (values[fieldname] !== undefined && values[fieldname] !== null && values[fieldname] !== "") {
					attributes[attribute] = values[fieldname];
				}
			});
			(values.additional_attributes || []).forEach((row) => {
				if (row.attribute && row.attribute_value) {
					attributes[row.attribute] = row.attribute_value;
				}
			});
			const payload = {
				template_item: options.template_item,
				attributes,
				uoms: (values.uoms || []).map((row) => ({
					uom: row.uom,
					conversion_factor: row.conversion_factor,
				})),
				source: frm
					? {
							doctype: frm.doctype,
							fieldname: grid_config.fieldname,
							document: frm.is_new() ? null : frm.doc.name,
					  }
					: null,
			};
			frappe.call({
				method: "srv_erp.masters.dynamic_item.api.resolve_or_request_item_variant",
				args: { payload },
				freeze: true,
				freeze_message: __("Resolving Item..."),
				callback(response) {
					const result = response.message;
					if (!result) return;
					dialog.hide();
					srv_erp.dynamic_item.handle_result(result, frm, grid_config);
				},
			});
		},
	});
	dialog.show();
};

srv_erp.dynamic_item.handle_result = function (result, frm, grid_config) {
	if (result.outcome === "existing") {
		if (!frm || !grid_config) {
			frappe.set_route("Form", "Item", result.item_code);
			return;
		}
		const grid = frm.fields_dict[grid_config.fieldname].grid;
		const selected = grid.get_selected_children ? grid.get_selected_children() : [];
		let row = selected.length === 1 ? selected[0] : null;
		if (!row || row.item_code) {
			row = frm.add_child(grid_config.fieldname);
		}
		frappe.model.set_value(row.doctype, row.name, "item_code", result.item_code).then(() => {
			frm.refresh_field(grid_config.fieldname);
		});
		return;
	}

	const request_link = frappe.utils.get_form_link("Dynamic Item Request", result.request, true);
	const item_text = result.item_code ? ` ${__("Staged Item")}: ${frappe.utils.escape_html(result.item_code)}.` : "";
	frappe.msgprint({
		title: __("Approval Required"),
		indicator: "orange",
		message: `${__("Request")} ${request_link} ${__("is pending approval")}.${item_text}`,
	});
};

$(document).on("form-refresh", (_event, frm) => {
	srv_erp.dynamic_item.configure_form(frm);
});
