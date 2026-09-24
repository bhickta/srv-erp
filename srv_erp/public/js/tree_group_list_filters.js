/* global srv_erp */

frappe.provide("srv_erp.list_view");


function normalize_tree_filter_values(value) {
	if (!value) {
		return [];
	}

	if (Array.isArray(value)) {
		return value.filter(Boolean);
	}

	return [value].filter(Boolean);
}


async function get_tree_group_descendants(listview, config, values) {
	if (!values.length) {
		return [];
	}

	return frappe.xcall(
		"srv_erp.tree_group_filters.get_tree_group_descendants",
		{
			doctype: listview.doctype,
			fieldname: config.fieldname,
			names: values,
		}
	);
}


function setup_single_tree_group_filter(listview, config) {
	const original_field =
		listview.page.fields_dict[config.fieldname];

	if (!original_field) {
		console.warn(
			`[${listview.doctype}] Tree filter field "${config.fieldname}" was not found.`
		);

		return;
	}

	listview.__srv_tree_group_filters =
		listview.__srv_tree_group_filters || {};

	if (listview.__srv_tree_group_filters[config.fieldname]) {
		return;
	}

	const initial_value = normalize_tree_filter_values(
		original_field.get_value?.()
	);

	const state = {
		selected_values: initial_value,
		expanded_values: [],
		request_id: 0,
	};

	original_field.$wrapper.hide();

	const custom_fieldname =
		`__srv_tree_${config.fieldname}`;

	const multi_select = listview.page.add_field({
		fieldname: custom_fieldname,
		label: config.label || original_field.df.label,
		fieldtype: "MultiSelectList",
		options: original_field.df.options,

		get_data(txt) {
			return frappe.db.get_link_options(
				original_field.df.options,
				txt,
				config.link_filters || {
					is_group: 1,
				}
			);
		},

		onchange: async function () {
			const selected_values =
				normalize_tree_filter_values(
					this.get_value()
				);

			state.selected_values = selected_values;

			const current_request_id =
				++state.request_id;

			if (!selected_values.length) {
				state.expanded_values = [];

				listview.refresh();

				return;
			}

			frappe.dom.freeze(
				__("Loading Tour groups...")
			);

			try {
				const expanded_values =
					await get_tree_group_descendants(
						listview,
						config,
						selected_values
					);

				if (
					current_request_id !==
					state.request_id
				) {
					return;
				}

				state.expanded_values =
					normalize_tree_filter_values(
						expanded_values
					);

				listview.refresh();

			} catch (error) {
				console.error(
					"[Tree Group Filter] Failed to resolve descendants",
					error
				);

				frappe.msgprint({
					title: __("Tour Filter Error"),
					message: __(
						"Unable to load the selected Tour groups."
					),
					indicator: "red",
				});

			} finally {
				frappe.dom.unfreeze();
			}
		},
	});

	if (multi_select?.$wrapper) {
		multi_select.$wrapper.insertBefore(
			original_field.$wrapper
		);
	}

	const original_get_filters_for_args =
		listview.get_filters_for_args.bind(listview);

	listview.get_filters_for_args = function () {
		const page_fields =
			listview.page.fields_dict;

		const custom_field =
			page_fields[custom_fieldname];

		if (custom_field) {
			delete page_fields[custom_fieldname];
		}

		let filters;

		try {
			filters =
				original_get_filters_for_args();
		} finally {
			if (custom_field) {
				page_fields[custom_fieldname] =
					custom_field;
			}
		}

		filters = filters.filter((filter) => {
			return !(
				Array.isArray(filter) &&
				filter[0] === listview.doctype &&
				filter[1] === config.fieldname
			);
		});

		if (state.expanded_values.length) {
			filters.push([
				listview.doctype,
				config.fieldname,
				"in",
				state.expanded_values,
			]);
		}

		return filters;
	};

	if (initial_value.length) {
		multi_select.set_value(initial_value);
	}

	listview.__srv_tree_group_filters[
		config.fieldname
	] = {
		control: multi_select,
		state,
	};
}


srv_erp.list_view.setup_tree_group_filters = function (
	listview,
	configs
) {
	configs.forEach((config) => {
		setup_single_tree_group_filter(listview, {
			doctype: listview.doctype,
			...config,
		});
	});
};