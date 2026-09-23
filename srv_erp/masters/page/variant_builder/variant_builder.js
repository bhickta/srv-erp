frappe.pages["variant-builder"].on_page_load = function (wrapper) {
	new srv_erp.masters.VariantBuilderPage(wrapper);
};

frappe.provide("srv_erp.masters");

const variant_builder_source_pills = {
	Brand: "green",
	"Template Override": "blue",
	"Template Profile": "gray",
	"Template Profile Fallback": "orange",
	"Brand Selection": "orange",
};

srv_erp.masters.VariantBuilderPage = class VariantBuilderPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Variant Builder"),
			single_column: true,
		});
		this.attribute_map = {};
		this.attribute_fields = [];
		this.attribute_form = null;
		this.options = null;
		this.enabled = false;
		this.make();
	}

	make() {
		this.$body = $(`
			<div class="variant-builder">
				<div class="variant-builder__intro text-muted">
					${__("Resolve or request a variant for any Item template using its effective Brand rules.")}
				</div>
				<div class="row">
					<div class="col-lg-8">
						<div class="frappe-card variant-builder__card">
							<div class="variant-builder__card-title">${__("Target")}</div>
							<div class="variant-builder-form"></div>
						</div>
					</div>
					<div class="col-lg-4">
						<div class="frappe-card variant-builder__card variant-builder__summary-card">
							<div class="variant-builder__card-title">${__("Configuration")}</div>
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
		this.page.add_inner_button(__("Preview"), () => this.preview());

		this.render_base_form();
		this.load_client_settings();
	}

	render_base_form() {
		const fields = [
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
				description: __("Drives the Brand Variant Rules."),
				onchange: () => this.on_brand_change(),
			},
			{ fieldtype: "HTML", fieldname: "attributes_html" },
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
		this.form = new frappe.ui.FieldGroup({ fields, body: this.$formArea });
		this.form.make();
		this.$attributeArea = $('<div class="variant-builder-attributes"></div>').appendTo(
			this.form.get_field("attributes_html").$wrapper
		);
	}

	on_template_change() {
		this.attribute_fields = [];
		this.attribute_map = {};
		this.options = null;
		this.clear_attributes();
		this.load_attributes();
	}

	on_brand_change() {
		if (!this.form.get_value("template_item")) {
			return;
		}
		this.load_attributes();
	}

	clear_attributes() {
		this.attribute_form = null;
		this.$attributeArea.empty();
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
					this.apply_options(options);
				}
			},
		});
	}

	apply_options(options) {
		this.attribute_fields = [];
		this.attribute_map = {};
		this.clear_attributes();
		this.options = options.requires_brand_selection ? null : options;

		if (!options.requires_brand_selection) {
			this.attribute_fields = (options.attributes || []).map((attribute, index) => {
				const fieldname = `variant_attribute_${index}`;
				this.attribute_map[fieldname] = attribute.attribute;
				const values = attribute.values || [];
				const is_brand = attribute.attribute.trim().toLowerCase() === "brand";
				const field = {
					fieldname,
					fieldtype: attribute.numeric_values ? "Float" : is_brand ? "Link" : "Select",
					label: attribute.attribute,
					options: attribute.numeric_values
						? null
						: is_brand
						? "Brand"
						: ["", ...values],
					default:
						!attribute.numeric_values && values.length === 1 ? values[0] : undefined,
					reqd: attribute.required ? 1 : 0,
					description: attribute.numeric_values
						? __("Enter a value within the configured numeric range.")
						: is_brand
						? __("Select a Brand.")
						: __("Select a predefined value."),
				};
				if (is_brand && values.length) {
					field.get_query = () => ({ filters: { name: ["in", values] } });
				}
				return field;
			});

			if (this.attribute_fields.length) {
				$('<div class="variant-builder__section-title">')
					.text(__("Variant Identity"))
					.appendTo(this.$attributeArea);
				const $fields = $('<div class="variant-builder-attribute-fields"></div>').appendTo(
					this.$attributeArea
				);
				this.attribute_form = new frappe.ui.FieldGroup({
					fields: this.attribute_fields,
					body: $fields,
				});
				this.attribute_form.make();
			}
		}

		this.render_summary(options);
		if (options.requires_brand_selection) {
			frappe.show_alert({
				message: __("Select a Brand to load its variant attributes."),
				indicator: "orange",
			});
		} else if (options.configuration_fallback) {
			frappe.show_alert({
				message: __("No published Brand rules; using the template profile."),
				indicator: "orange",
			});
		}
	}

	render_summary(options) {
		const escape = frappe.utils.escape_html;
		const template = escape(options.template_item || "");

		if (options.requires_brand_selection) {
			this.$summary.html(`
				<div class="variant-builder__summary-template">${template}</div>
				<div class="text-muted">${__("Select a Brand to load its variant attributes.")}</div>
			`);
			return;
		}

		const source = options.configuration_source || "-";
		const pill = variant_builder_source_pills[source] || "gray";
		const revision = options.configuration_revision
			? escape(String(options.configuration_revision))
			: "-";
		const rules = (options.attributes || [])
			.map(
				(attribute) => `
					<li>
						<span>${escape(attribute.attribute)}</span>
						${attribute.required ? `<span class="indicator-pill green">${__("Required")}</span>` : ""}
						<span class="text-muted">${
							attribute.numeric_values
								? __("Numeric range")
								: escape(
										(attribute.values || []).join(", ") ||
											__("No predefined values")
								  )
						}</span>
					</li>`
			)
			.join("");
		this.$summary.html(`
			<div class="variant-builder__summary-template">${template}</div>
			<div class="variant-builder__summary-meta">
				<span class="indicator-pill ${pill}">${escape(source)}</span>
				<span class="text-muted">${__("Revision")} ${revision}</span>
			</div>
			${
				options.configuration_fallback
					? `<div class="text-muted">${__(
							"No published Brand rules; using the template profile."
					  )}</div>`
					: ""
			}
			<div class="variant-builder__section-title">${__("Variant Attributes")}</div>
			<ul class="variant-builder__rules">${
				rules || `<li class="text-muted">${__("No variant attributes configured.")}</li>`
			}</ul>
		`);
	}

	load_client_settings() {
		frappe.call({
			method: "srv_erp.masters.dynamic_item.api.get_dynamic_item_client_settings",
			callback: (response) => {
				const settings = response.message || {};
				this.enabled = Boolean(settings.enabled);
				if (!this.enabled) {
					this.render_unavailable(settings);
					return;
				}
				const brand_field = this.form.get_field("brand");
				brand_field?.toggle(Boolean(settings.brand_variant_rules_enabled));
			},
		});
	}

	render_unavailable(settings) {
		let reason = __("You do not have a role that can request Items.");
		if (settings.feature_enabled === false) {
			reason = __("Dynamic Item Requests are disabled in Masters Settings.");
		}
		const can_configure =
			settings.feature_enabled === false && frappe.user.has_role("System Manager");
		this.$formArea.html(`
			<div class="alert alert-warning">
				${frappe.utils.escape_html(reason)}
				${
					can_configure
						? `<div class="mt-2">${__(
								"Enable Dynamic Item Requests (with at least one Requester Role) to use this page."
						  )}</div>`
						: ""
				}
			</div>
		`);
		this.$summary.html(
			`<div class="text-muted">${__("Variant Builder is unavailable.")}</div>`
		);
		this.page.clear_primary_action();
		if (can_configure) {
			this.page.add_inner_button(__("Open Masters Settings"), () =>
				frappe.set_route("Form", "Masters Settings")
			);
		}
	}

	collect_payload() {
		const base = this.form.get_values();
		if (!base) {
			return null;
		}
		const attribute_values = this.attribute_form ? this.attribute_form.get_values() : {};
		if (!attribute_values) {
			return null;
		}
		const attributes = {};
		Object.entries(this.attribute_map).forEach(([fieldname, attribute]) => {
			const value = attribute_values[fieldname];
			if (value !== undefined && value !== null && value !== "") {
				attributes[attribute] = value;
			}
		});
		return {
			template_item: base.template_item,
			attributes,
			uoms: (base.uoms || []).map((row) => ({
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
	.variant-builder__intro {
		margin-bottom: 16px;
	}
	.variant-builder__card {
		padding: 16px;
	}
	.variant-builder__card-title {
		font-weight: 600;
		margin-bottom: 12px;
	}
	.variant-builder__section-title {
		font-weight: 600;
		margin: 16px 0 8px;
	}
	.variant-builder__summary-template {
		font-weight: 600;
		margin-bottom: 8px;
	}
	.variant-builder__summary-meta {
		align-items: center;
		display: flex;
		gap: 8px;
		margin-bottom: 8px;
	}
	.variant-builder__rules {
		list-style: none;
		margin: 0;
		padding-left: 0;
	}
	.variant-builder__rules li {
		align-items: center;
		border-bottom: 1px solid var(--border-color);
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		padding: 6px 0;
	}
	.variant-builder__rules li:last-child {
		border-bottom: none;
	}
	@media (min-width: 992px) {
		.variant-builder__summary-card {
			position: sticky;
			top: 15px;
		}
	}
`);
