frappe.pages["variant-builder"].on_page_load = function (wrapper) {
	new srv_erp.masters.VariantBuilderPage(wrapper);
};

frappe.provide("srv_erp.masters");

srv_erp.masters.VariantBuilderPage = class VariantBuilderPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Variant Builder"),
			single_column: true,
		});
		this.attribute_map = {};
		this.attribute_fields = [];
		this.options = null;
		this.enabled = false;
		this._applying = false;
		this.make();
	}

	make() {
		this.$body = $(`
			<div class="variant-builder">
				<div class="row">
					<div class="col-md-8">
						<div class="frappe-card variant-builder__form-card">
							<div class="variant-builder-form"></div>
						</div>
					</div>
					<div class="col-md-4">
						<div class="frappe-card variant-builder__summary-card">
							<div class="variant-builder-summary text-muted">
								${__("Select an Item Template to begin.")}
							</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.$formArea = this.$body.find(".variant-builder-form");
		this.$summary = this.$body.find(".variant-builder-summary");

		this.page.set_primary_action(__("Resolve / Request Variant"), () => this.submit(), "add");
		this.page.add_inner_button(__("Load Attributes"), () => this.load_attributes());
		this.page.add_inner_button(__("Preview"), () => this.preview());

		this.render_form();
		this.load_client_settings();
	}

	load_client_settings() {
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.get_dynamic_item_client_settings",
			callback: (response) => {
				const settings = response.message || {};
				this.enabled = Boolean(settings.enabled);
				if (!this.enabled) {
					this.$formArea.html(
						`<div class="alert alert-warning">${__(
							"Dynamic Item Requests are disabled or you do not have permission to request Items."
						)}</div>`
					);
					this.$summary.html(
						`<div class="text-muted">${__("Variant Builder is unavailable.")}</div>`
					);
					this.page.clear_primary_action();
				}
			},
		});
	}

	base_fields() {
		return [
			{
				fieldtype: "Link",
				fieldname: "template_item",
				label: __("Item Template"),
				options: "Item",
				reqd: 1,
				get_query: () => ({
					filters: {
						has_variants: 1,
						variant_based_on: "Item Attribute",
						disabled: 0,
					},
				}),
				onchange: () => this.on_template_change(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Link",
				fieldname: "brand",
				label: __("Brand"),
				options: "Brand",
				description: __("Optional; required when the template resolves Brand rules."),
				onchange: () => this.load_attributes(),
			},
		];
	}

	uom_fields() {
		return [
			{ fieldtype: "Section Break", label: __("Packaging UOMs (optional)") },
			{
				fieldtype: "Table",
				fieldname: "uoms",
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
		];
	}

	render_form(preserve = {}) {
		const fields = [...this.base_fields()];
		if (this.attribute_fields.length) {
			fields.push({ fieldtype: "Section Break", label: __("Variant Identity") });
			fields.push(...this.attribute_fields);
		}
		fields.push(...this.uom_fields());

		this._applying = true;
		this.$formArea.empty();
		this.form = new frappe.ui.FieldGroup({ fields, body: this.$formArea });
		this.form.make();
		if (preserve.template_item) {
			this.form.set_value("template_item", preserve.template_item);
		}
		if (preserve.brand) {
			this.form.set_value("brand", preserve.brand);
		}
		this._applying = false;
	}

	on_template_change() {
		if (this._applying) {
			return;
		}
		const template_item = this.form.get_value("template_item");
		const brand = this.form.get_value("brand");
		this.attribute_fields = [];
		this.attribute_map = {};
		this.options = null;
		this.$summary.html(`<div class="text-muted">${__("Loading variant attributes...")}</div>`);
		setTimeout(() => {
			this.render_form({ template_item, brand });
			this.load_attributes();
		}, 0);
	}

	load_attributes() {
		if (!this.enabled) {
			return;
		}
		const template_item = this.form.get_value("template_item");
		const selected_brand = this.form.get_value("brand");
		if (!template_item) {
			frappe.msgprint(__("Select an Item Template first."));
			return;
		}
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.get_dynamic_variant_options",
			args: { template_item, selected_brand: selected_brand || undefined },
			freeze: true,
			freeze_message: __("Loading variant attributes..."),
			callback: (response) => {
				const options = response.message;
				if (options) {
					this.apply_options(options, template_item, selected_brand);
				}
			},
		});
	}

	apply_options(options, template_item, selected_brand) {
		this.attribute_map = {};
		if (options.requires_brand_selection) {
			this.options = null;
			this.attribute_fields = [];
			this.render_form({ template_item, brand: selected_brand });
			this.render_summary(options);
			frappe.show_alert({
				message: __("Select a Brand to load its variant attributes."),
				indicator: "orange",
			});
			return;
		}

		this.options = options;
		this.attribute_fields = (options.attributes || []).map((attribute, index) => {
			const fieldname = `variant_attribute_${index}`;
			this.attribute_map[fieldname] = attribute.attribute;
			const values = attribute.values || [];
			return {
				fieldname,
				fieldtype: attribute.numeric_values ? "Float" : "Select",
				label: attribute.attribute,
				options: attribute.numeric_values ? null : ["", ...values],
				default: !attribute.numeric_values && values.length === 1 ? values[0] : undefined,
				reqd: attribute.required ? 1 : 0,
				description: attribute.numeric_values
					? __("Enter a value within the configured numeric range.")
					: __("Select a predefined value."),
			};
		});
		this.render_form({ template_item, brand: selected_brand });
		this.render_summary(options);
	}

	render_summary(options) {
		const escape = frappe.utils.escape_html;
		const source = options.requires_brand_selection
			? __("Brand Selection")
			: escape(options.configuration_source || "-");
		const revision = options.configuration_revision
			? escape(String(options.configuration_revision))
			: "-";
		const rules = (options.attributes || [])
			.map(
				(attribute) =>
					`<li><strong>${escape(attribute.attribute)}</strong>${
						attribute.required
							? ` <span class="indicator-pill green">${__("Required")}</span>`
							: ""
					} — ${
						attribute.numeric_values
							? __("Numeric range")
							: escape(
									(attribute.values || []).join(", ") ||
										__("No predefined values")
							  )
					}</li>`
			)
			.join("");
		this.$summary.html(`
			<div class="variant-builder-summary__title">${escape(options.template_item || "")}</div>
			<div><strong>${__("Source")}:</strong> ${source}</div>
			<div><strong>${__("Revision")}:</strong> ${revision}</div>
			${
				options.configuration_fallback
					? `<div class="text-muted">${__(
							"No published Brand rules; using the template profile."
					  )}</div>`
					: ""
			}
			<ul class="mt-3">${rules || `<li>${__("No variant attributes configured.")}</li>`}</ul>
		`);
	}

	collect_payload() {
		const values = this.form.get_values();
		if (!values) {
			return null;
		}
		const attributes = {};
		Object.entries(this.attribute_map).forEach(([fieldname, attribute]) => {
			const value = values[fieldname];
			if (value !== undefined && value !== null && value !== "") {
				attributes[attribute] = value;
			}
		});
		return {
			template_item: values.template_item,
			attributes,
			uoms: (values.uoms || []).map((row) => ({
				uom: row.uom,
				conversion_factor: row.conversion_factor,
			})),
			source: null,
		};
	}

	submit() {
		if (!this.require_loaded()) {
			return;
		}
		const payload = this.collect_payload();
		if (!payload) {
			return;
		}
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.resolve_or_request_item_variant",
			args: { payload },
			freeze: true,
			freeze_message: __("Resolving Item..."),
			callback: (response) => this.handle_result(response.message),
		});
	}

	preview() {
		if (!this.require_loaded()) {
			return;
		}
		const payload = this.collect_payload();
		if (!payload) {
			return;
		}
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.preview_dynamic_item_variant",
			args: { payload },
			freeze: true,
			freeze_message: __("Previewing variant..."),
			callback: (response) => {
				const result = response.message;
				if (!result) {
					return;
				}
				if (result.existing_item) {
					frappe.msgprint({
						title: __("Variant Exists"),
						indicator: "green",
						message: __("Variant {0} already exists.", [
							frappe.utils.escape_html(result.existing_item),
						]),
					});
					return;
				}
				frappe.msgprint({
					title: __("New Variant"),
					indicator: "blue",
					message: __("No matching variant exists. Creating it will require approval."),
				});
			},
		});
	}

	require_loaded() {
		if (!this.enabled) {
			return false;
		}
		if (!this.options) {
			frappe.msgprint(__("Load the variant attributes for the selected template first."));
			return false;
		}
		return true;
	}

	handle_result(result) {
		if (!result) {
			return;
		}
		const escape = frappe.utils.escape_html;
		if (result.outcome === "existing") {
			frappe.show_alert({
				message: __("Variant {0} already exists.", [escape(result.item_code)]),
				indicator: "green",
			});
			frappe.set_route("Form", "Item", result.item_code);
			return;
		}
		const request_link = frappe.utils.get_form_link(
			"Dynamic Item Request",
			result.request,
			true
		);
		const item_text = result.item_code
			? ` ${__("Staged Item")}: ${escape(result.item_code)}.`
			: "";
		const is_packaging = result.outcome === "packaging_approval_required";
		frappe.msgprint({
			title: is_packaging ? __("Packaging Approval Required") : __("Approval Required"),
			indicator: "orange",
			message: `${__("Request")} ${request_link} ${__("is pending approval")}.${item_text}`,
		});
	}
};

frappe.dom.set_style(`
	.variant-builder__form-card,
	.variant-builder__summary-card {
		padding: 16px;
	}
	.variant-builder-summary__title {
		font-weight: 600;
		margin-bottom: 8px;
	}
`);
