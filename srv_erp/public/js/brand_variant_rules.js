frappe.provide("srv_erp.brand_variant_rules");

srv_erp.brand_variant_rules = {
	refresh(frm) {
		if (frm.is_new() || !frm.fields_dict.brand_variant_rules_section) return;
		frappe.call({
			method: "srv_erp.masters.dynamic_item.brand_rules_api.get_brand_variant_rules_state",
			args: { brand: frm.doc.name },
			callback: (response) => {
				const state = response.message || {};
				frm.toggle_display("brand_variant_rules_section", Boolean(state.enabled));
				if (state.enabled) srv_erp.brand_variant_rules.render(frm, state);
			},
		});
	},

	render(frm, state) {
		const field = frm.fields_dict.brand_variant_rules_html;
		if (!field?.$wrapper) return;
		const escape = frappe.utils.escape_html;
		const rules = state.rules || [];
		const summary = rules.length
			? rules
					.map(
						(rule) =>
							`<li><strong>${escape(rule.attribute)}</strong>${
								rule.required
									? ` <span class="indicator-pill green">${__(
											"Required"
									  )}</span>`
									: ""
							} — ${escape(
								(rule.values || []).join(", ") || __("Numeric template range")
							)}</li>`
					)
					.join("")
			: `<li>${__("No draft rules configured.")}</li>`;
		field.$wrapper.html(`
			<div class="form-message blue">
				<div><strong>${__("Publication")}:</strong> ${escape(state.publication_status)}
					&middot; <strong>${__("Revision")}:</strong> ${state.published_revision || 0}
					&middot; <strong>${__("Sync")}:</strong> ${escape(state.sync_status)}</div>
				${
					state.last_sync_message
						? `<div class="text-muted">${escape(state.last_sync_message)}</div>`
						: ""
				}
			</div>
			<ul class="mt-3">${summary}</ul>
			<div class="mt-3">
				${
					state.can_manage
						? `<button class="btn btn-xs btn-default" data-action="edit">${__(
								"Edit Draft"
						  )}</button>
				<button class="btn btn-xs btn-primary" data-action="publish">${__("Preview and Publish")}</button>
				<button class="btn btn-xs btn-default" data-action="retry">${__("Retry Sync")}</button>`
						: ""
				}
				<button class="btn btn-xs btn-default" data-action="conflicts">${__("View Conflicts")}</button>
			</div>`);
		field.$wrapper
			.find('[data-action="edit"]')
			.on("click", () => this.open_editor(frm, state));
		field.$wrapper.find('[data-action="publish"]').on("click", () => this.publish(frm));
		field.$wrapper.find('[data-action="retry"]').on("click", () => this.retry(frm));
		field.$wrapper.find('[data-action="conflicts"]').on("click", () => {
			frappe.route_options = { brand: frm.doc.name, status: "Open" };
			frappe.set_route("query-report", "Brand Variant Rule Conflicts");
		});
	},

	open_editor(frm, state) {
		const data = (state.rules || []).map((rule) => ({
			attribute: rule.attribute,
			required: rule.required ? 1 : 0,
			allowed_values: (rule.values || []).join(", "),
		}));
		const dialog = new frappe.ui.Dialog({
			title: __("Brand Variant Attributes: {0}", [frm.doc.name]),
			size: "extra-large",
			fields: [
				{
					fieldname: "rules",
					fieldtype: "Table",
					label: __("Draft Rules"),
					data,
					in_place_edit: true,
					fields: [
						{
							fieldname: "attribute",
							fieldtype: "Link",
							options: "Item Attribute",
							label: __("Item Attribute"),
							reqd: 1,
							in_list_view: 1,
						},
						{
							fieldname: "required",
							fieldtype: "Check",
							label: __("Required"),
							in_list_view: 1,
						},
						{
							fieldname: "allowed_values",
							fieldtype: "Small Text",
							label: __("Allowed Values (comma separated)"),
							in_list_view: 1,
						},
					],
				},
			],
			primary_action_label: __("Save Draft"),
			primary_action(values) {
				const rules = (values.rules || []).map((row) => ({
					attribute: row.attribute,
					required: row.required,
					values: (row.allowed_values || "")
						.split(",")
						.map((value) => value.trim())
						.filter(Boolean),
				}));
				frappe.call({
					method: "srv_erp.masters.dynamic_item.brand_rules_api.save_brand_variant_rules_draft",
					args: { brand: frm.doc.name, rules },
					freeze: true,
					callback: () => {
						dialog.hide();
						srv_erp.brand_variant_rules.refresh(frm);
					},
				});
			},
		});
		dialog.show();
	},

	publish(frm) {
		frappe.confirm(
			__(
				"Publish this draft for future variant requests? Existing variants will only be reported as conflicts."
			),
			() => {
				frappe.call({
					method: "srv_erp.masters.dynamic_item.brand_rules_api.publish_brand_variant_rules",
					args: { brand: frm.doc.name },
					freeze: true,
					callback: () => this.refresh(frm),
				});
			}
		);
	},

	retry(frm) {
		frappe.call({
			method: "srv_erp.masters.dynamic_item.brand_rules_api.retry_brand_variant_rule_sync",
			args: { brand: frm.doc.name },
			callback: () => this.refresh(frm),
		});
	},
};

frappe.ui.form.on("Brand", {
	refresh(frm) {
		srv_erp.brand_variant_rules.refresh(frm);
	},
});
