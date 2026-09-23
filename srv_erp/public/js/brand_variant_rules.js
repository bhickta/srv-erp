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
				<button class="btn btn-xs btn-default" data-action="retry">${__("Retry Sync")}</button>
				<button class="btn btn-xs btn-default" data-action="defaults">${__("Apply Defaults")}</button>`
						: ""
				}
				<button class="btn btn-xs btn-default" data-action="conflicts">${__("View Conflicts")}</button>
			</div>`);
		field.$wrapper
			.find('[data-action="edit"]')
			.on("click", () => this.open_editor(frm, state));
		field.$wrapper.find('[data-action="publish"]').on("click", () => this.publish(frm));
		field.$wrapper.find('[data-action="retry"]').on("click", () => this.retry(frm));
		field.$wrapper
			.find('[data-action="defaults"]')
			.on("click", () => this.open_default_backfill(frm));
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
			confidence: rule.confidence,
			note: rule.note,
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
						{
							fieldname: "confidence",
							fieldtype: "Select",
							options: "\nHigh\nLow",
							label: __("Confidence"),
							read_only: 1,
							in_list_view: 1,
						},
						{
							fieldname: "note",
							fieldtype: "Small Text",
							label: __("Suggestion Note"),
							read_only: 1,
						},
					],
				},
				{ fieldname: "generate", fieldtype: "Button", label: __("Generate Suggestions") },
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
					confidence: row.confidence,
					note: row.note,
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
		dialog.fields_dict.generate.$input.on("click", () => {
			frappe.call({
				method: "srv_erp.masters.dynamic_item.brand_rules_api.generate_brand_variant_rule_suggestions",
				args: { brand: frm.doc.name },
				callback: (response) => {
					dialog.fields_dict.rules.df.data = (response.message || []).map((rule) => ({
						...rule,
						allowed_values: (rule.values || []).join(", "),
					}));
					dialog.fields_dict.rules.grid.refresh();
				},
			});
		});
		dialog.show();
	},

	open_default_backfill(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Apply Item Group Defaults: {0}", [frm.doc.name]),
			size: "large",
			fields: [
				{
					fieldname: "item_group",
					fieldtype: "Link",
					options: "Item Group",
					label: __("Item Group (optional)"),
					description: __("Limit to this Item Group and its child groups."),
				},
				{
					fieldname: "template_item",
					fieldtype: "Link",
					options: "Item",
					label: __("Item Template (optional)"),
					get_query: () => ({
						filters: { has_variants: 1, variant_based_on: "Item Attribute" },
					}),
				},
				{ fieldname: "preview_result", fieldtype: "HTML" },
			],
			primary_action_label: __("Apply"),
			primary_action(values) {
				frappe.confirm(
					__(
						"Apply the defaults to the affected existing variants? Attributes are only added, never overwritten."
					),
					() => {
						frappe.call({
							method: "srv_erp.masters.dynamic_item.brand_default_backfill.apply_brand_default_backfill",
							args: {
								brand: frm.doc.name,
								item_group: values.item_group || undefined,
								template_item: values.template_item || undefined,
							},
							freeze: true,
							freeze_message: __("Applying defaults..."),
							callback: (response) => {
								dialog.hide();
								srv_erp.brand_variant_rules.show_backfill_result(
									response.message || {}
								);
							},
						});
					}
				);
			},
		});
		dialog.set_secondary_action_label(__("Preview"));
		dialog.set_secondary_action(() => {
			const values = dialog.get_values();
			if (!values) {
				return;
			}
			frappe.call({
				method: "srv_erp.masters.dynamic_item.brand_default_backfill.preview_brand_default_backfill",
				args: {
					brand: frm.doc.name,
					item_group: values.item_group || undefined,
					template_item: values.template_item || undefined,
				},
				freeze: true,
				callback: (response) => {
					srv_erp.brand_variant_rules.render_backfill_preview(
						dialog.fields_dict.preview_result.$wrapper,
						response.message || {}
					);
				},
			});
		});
		dialog.show();
	},

	render_backfill_preview($wrapper, result) {
		const escape = frappe.utils.escape_html;
		const changes = result.changes || [];
		const conflicts = result.conflicts || [];
		const ignored = result.ignored || [];
		const change_rows = changes
			.map(
				(change) =>
					`<tr><td>${escape(change.item_code)}</td><td>${escape(
						change.template_item
					)}</td><td>${escape(
						Object.entries(change.attributes || {})
							.map(([attribute, value]) => `${attribute}: ${value}`)
							.join(", ")
					)}</td></tr>`
			)
			.join("");
		const conflict_rows = conflicts
			.map(
				(conflict) =>
					`<tr><td>${escape(conflict.item_code)}</td><td>${escape(
						conflict.template_item
					)}</td><td>${escape(conflict.reason)}</td></tr>`
			)
			.join("");
		const ignored_rows = ignored
			.map(
				(entry) =>
					`<li>${escape(entry.template_item)} — ${escape(entry.attribute)}: ${escape(
						entry.value
					)} (${escape(entry.reason)})</li>`
			)
			.join("");
		$wrapper.html(`
			<div class="mt-3">
				<div><strong>${__("Variants to update")}:</strong> ${changes.length}
					&middot; <strong>${__("Conflicts")}:</strong> ${conflicts.length}</div>
				${
					change_rows
						? `<table class="table table-bordered table-sm mt-2">
					<thead><tr><th>${__("Variant")}</th><th>${__("Template")}</th><th>${__(
								"Attributes to add"
						  )}</th></tr></thead>
					<tbody>${change_rows}</tbody></table>`
						: `<div class="text-muted">${__("No variants need updating.")}</div>`
				}
				${
					conflict_rows
						? `<div class="mt-2"><strong>${__("Skipped")}</strong>
					<table class="table table-bordered table-sm mt-2">
					<thead><tr><th>${__("Variant")}</th><th>${__("Template")}</th><th>${__("Reason")}</th></tr></thead>
					<tbody>${conflict_rows}</tbody></table></div>`
						: ""
				}
				${
					ignored_rows
						? `<div class="mt-2"><strong>${__(
								"Ignored defaults"
						  )}</strong><ul>${ignored_rows}</ul></div>`
						: ""
				}
			</div>
		`);
	},

	show_backfill_result(result) {
		if (result.queued) {
			frappe.show_alert({
				message: __("{0} defaults queued for application.", [result.change_count || 0]),
				indicator: "blue",
			});
			return;
		}
		frappe.show_alert({
			message: __("Applied {0} default(s); {1} failed.", [
				result.applied || 0,
				result.failed || 0,
			]),
			indicator: result.failed ? "orange" : "green",
		});
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
