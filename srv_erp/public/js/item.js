frappe.provide("erpnext.item");

$.extend(erpnext.item, {
	show_multiple_variants_dialog: function (frm) {
		var me = this;

		let promises = [];
		let attr_val_fields = {};

		function get_select_all_fieldname(attribute) {
			return `select_all_${frappe.scrub(attribute)}`;
		}

		function update_primary_action() {
			let selected_attributes = get_selected_attributes();
			let lengths = Object.keys(selected_attributes).map((key) => {
				return selected_attributes[key].length;
			});

			if (!lengths.length) {
				me.multiple_variant_dialog.get_primary_btn().html(__("Create Variants"));
				me.multiple_variant_dialog.disable_primary_action();
				return;
			}

			let no_of_combinations = lengths.reduce((a, b) => a * b, 1);
			let msg;
			if (no_of_combinations === 1) {
				msg = __("Make {0} Variant", [no_of_combinations]);
			} else {
				msg = __("Make {0} Variants", [no_of_combinations]);
			}
			me.multiple_variant_dialog.get_primary_btn().html(msg);
			me.multiple_variant_dialog.enable_primary_action();
		}

		function get_visible_attribute_values(attribute) {
			return attr_val_fields[attribute].filter((attr_value) => {
				let field = me.multiple_variant_dialog.fields_dict[attr_value];
				return field && !field.df.hidden;
			});
		}

		function set_attribute_values(attribute, checked) {
			get_visible_attribute_values(attribute).forEach((attr_value) => {
				me.multiple_variant_dialog.set_value(attr_value, checked ? 1 : 0);
			});
			update_primary_action();
		}

		function update_select_all(attribute) {
			let values = get_visible_attribute_values(attribute);
			let checked_values = values.filter((attr_value) => {
				return me.multiple_variant_dialog.get_value(attr_value);
			});
			let select_all_fieldname = get_select_all_fieldname(attribute);

			let select_all_field = me.multiple_variant_dialog.fields_dict[select_all_fieldname];
			if (select_all_field) {
				select_all_field.set_input(values.length && values.length === checked_values.length ? 1 : 0);
			}
		}

		function make_fields_from_attribute_values(attr_dict) {
			let fields = [];
			let att_key = frm.doc.attributes.map((idx) => idx.attribute);
			att_key.forEach((name, i) => {
				if (i % 3 === 0) {
					fields.push({ fieldtype: "Section Break" });
				}
				fields.push({ fieldtype: "Column Break", label: name });
				fields.push({
					fieldtype: "Check",
					label: __("Select All"),
					fieldname: get_select_all_fieldname(name),
					default: 0,
					onchange: function () {
						set_attribute_values(name, this.get_value());
					},
				});
				fields.push({
					fieldtype: "Data",
					placeholder: "Search",
					fieldname: `search_${frappe.scrub(name)}`,
					onchange: function (e) {
						let value = e.target.value;
						let result = attr_dict[name].filter((attr_value) =>
							attr_value.toString().toLowerCase().includes(value.toLowerCase())
						);
						attr_dict[name].forEach((attr_value) => {
							if (result.includes(attr_value)) {
								me.multiple_variant_dialog.set_df_property(attr_value, "hidden", 0);
							} else {
								me.multiple_variant_dialog.set_df_property(attr_value, "hidden", 1);
							}
						});
						update_select_all(name);
					},
				});
				attr_dict[name].forEach((value) => {
					fields.push({
						fieldtype: "Check",
						label: value,
						fieldname: value,
						default: 0,
						onchange: function () {
							update_select_all(name);
							update_primary_action();
						},
					});
				});
			});
			return fields;
		}

		function make_and_show_dialog(fields) {
			me.multiple_variant_dialog = new frappe.ui.Dialog({
				title: __("Select Attribute Values"),
				fields: [
					frm.doc.image
						? {
								fieldtype: "Check",
								label: __("Create a variant with the template image."),
								fieldname: "use_template_image",
								default: 0,
						  }
						: null,
					{
						fieldtype: "HTML",
						fieldname: "help",
						options: `<label class="control-label">
							${__("Select at least one attribute value.")}
						</label>`,
					},
				]
					.concat(fields)
					.filter(Boolean),
			});

			me.multiple_variant_dialog.set_primary_action(__("Create Variants"), () => {
				let selected_attributes = get_selected_attributes();
				let use_template_image = me.multiple_variant_dialog.get_value("use_template_image");

				me.multiple_variant_dialog.hide();
				frappe.call({
					method: "erpnext.controllers.item_variant.enqueue_multiple_variant_creation",
					args: {
						item: frm.doc.name,
						args: selected_attributes,
						use_template_image: use_template_image,
					},
					callback: function (r) {
						if (r.message === "queued") {
							frappe.show_alert({
								message: __("Variant creation has been queued."),
								indicator: "orange",
							});
						} else {
							frappe.show_alert({
								message: __("{0} variants created.", [r.message]),
								indicator: "green",
							});
						}
					},
				});
			});

			$($(me.multiple_variant_dialog.$wrapper.find(".form-column")).find(".frappe-control")).css(
				"margin-bottom",
				"0px"
			);

			me.multiple_variant_dialog.disable_primary_action();
			me.multiple_variant_dialog.clear();
			me.multiple_variant_dialog.show();
			me.multiple_variant_dialog.$wrapper
				.find("div[data-fieldname^='search_']")
				.find(".clearfix")
				.hide();
		}

		function get_selected_attributes() {
			let selected_attributes = {};
			me.multiple_variant_dialog.$wrapper.find(".form-column").each((i, col) => {
				if (i === 0) return;
				let attribute_name = $(col).find(".column-label").html().trim();
				selected_attributes[attribute_name] = [];
				let checked_opts = $(col).find(".checkbox input");
				checked_opts.each((i, opt) => {
					let fieldname = $(opt).attr("data-fieldname");
					if ($(opt).is(":checked") && fieldname && !fieldname.startsWith("select_all_")) {
						selected_attributes[attribute_name].push(fieldname);
					}
				});
				if (!selected_attributes[attribute_name].length) {
					delete selected_attributes[attribute_name];
				}
			});

			return selected_attributes;
		}

		frm.doc.attributes.forEach(function (d) {
			if (!d.disabled) {
				let p = new Promise((resolve) => {
					if (!d.numeric_values) {
						frappe
							.call({
								method: "frappe.client.get_list",
								args: {
									doctype: "Item Attribute Value",
									filters: [["parent", "=", d.attribute]],
									fields: ["attribute_value"],
									limit_page_length: 0,
									parent: "Item Attribute",
									order_by: "idx",
								},
							})
							.then((r) => {
								if (r.message) {
									attr_val_fields[d.attribute] = r.message.map(function (d) {
										return d.attribute_value;
									});
									resolve();
								}
							});
					} else {
						let values = [];
						for (var i = d.from_range; i <= d.to_range; i = flt(i + d.increment, 6)) {
							values.push(i);
						}
						attr_val_fields[d.attribute] = values;
						resolve();
					}
				});

				promises.push(p);
			}
		}, this);

		Promise.all(promises).then(() => {
			let fields = make_fields_from_attribute_values(attr_val_fields);
			make_and_show_dialog(fields);
		});
	},
});
