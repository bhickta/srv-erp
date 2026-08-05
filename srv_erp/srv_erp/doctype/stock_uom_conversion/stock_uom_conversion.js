// Copyright (c) 2026, Nishant Bhickta and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock UOM Conversion", {
	refresh: function (frm) {
		frm.trigger("set_page_indicator");
		frm.trigger("setup_dashboard");
		frm.trigger("setup_item_indicators");

		if (frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(
				__(
					'Click <b>Analyze</b> to preview all affected items, then <b>Submit</b> to execute the conversion.'
				),
				"blue"
			);

			let can_analyze = false;
			if (frm.doc.selection_mode === "Single Item" && frm.doc.item_code && frm.doc.new_stock_uom) {
				can_analyze = true;
			} else if (frm.doc.selection_mode === "Batch Filter" && frm.doc.new_stock_uom) {
				can_analyze = true;
			}

			if (can_analyze && (!frm.doc.items || frm.doc.items.length === 0)) {
				frm.page.set_primary_action(__("Analyze"), function () {
					frm.call("analyze").then(() => {
						frm.dirty();
						frm.refresh();
						frappe.show_alert({
							message: __("Analysis complete — review the Affected Items table below."),
							indicator: "green",
						});
					});
				});
			} else if (can_analyze && frm.doc.items && frm.doc.items.length > 0) {
				frm.add_custom_button(__("Re-Analyze"), function () {
					frm.call("analyze").then(() => {
						frm.dirty();
						frm.refresh();
						frappe.show_alert({
							message: __("Analysis complete — review the Affected Items table below."),
							indicator: "green",
						});
					});
				});
			}
		}
	},

	set_page_indicator: function (frm) {
		if (frm.doc.docstatus === 1) {
			// Check if any items failed
			let has_failure = (frm.doc.items || []).some(
				(d) => d.status === "Failed"
			);
			if (has_failure) {
				frm.page.set_indicator(__("Completed with Errors"), "orange");
			} else {
				frm.page.set_indicator(__("Converted"), "green");
			}
		} else if (frm.doc.docstatus === 2) {
			frm.page.set_indicator(__("Cancelled"), "red");
		} else if (frm.doc.items && frm.doc.items.length > 0) {
			frm.page.set_indicator(__("Analyzed"), "blue");
		} else {
			frm.page.set_indicator(__("Draft"), "orange");
		}
	},

	setup_dashboard: function (frm) {
		if (frm.is_new()) return;

		frm.dashboard.add_transactions({
			label: __("Audit Trail"),
			items: ["Stock UOM Conversion Log"],
		});
	},

	setup_item_indicators: function (frm) {
		if (!frm.fields_dict.items) return;
		let grid = frm.fields_dict.items.grid;

		// Color-code the strategy column
		grid.update_docfield_property(
			"strategy",
			"formatter",
			function (value) {
				if (value === "Direct")
					return `<span class="indicator-pill whitespace-nowrap green">${__(value)}</span>`;
				if (value === "Duplicate & Disable")
					return `<span class="indicator-pill whitespace-nowrap orange">${__(value)}</span>`;
				return value || "";
			}
		);

		// Color-code the status column
		grid.update_docfield_property(
			"status",
			"formatter",
			function (value) {
				const colors = {
					Converted: "green",
					Failed: "red",
					Pending: "yellow",
					Skipped: "grey",
				};
				let color = colors[value] || "grey";
				return `<span class="indicator-pill whitespace-nowrap ${color}">${__(value)}</span>`;
			}
		);

		// Color-code has_transactions check
		grid.update_docfield_property(
			"has_transactions",
			"formatter",
			function (value) {
				if (value)
					return '<span class="indicator-pill whitespace-nowrap red">Yes</span>';
				return '<span class="indicator-pill whitespace-nowrap green">No</span>';
			}
		);
	},

	item_code: function (frm) {
		if (!frm.doc.item_code) {
			frm.set_value("item_type", "");
			frm.set_value("variant_of", "");
			return;
		}

		frappe.db
			.get_value("Item", frm.doc.item_code, [
				"has_variants",
				"variant_of",
			])
			.then((r) => {
				let values = r.message;
				if (!values) return;

				let item_type = "Standard";
				if (values.has_variants) item_type = "Template";
				else if (values.variant_of) item_type = "Variant";

				frm.set_value("item_type", item_type);
				frm.set_value("variant_of", values.variant_of || "");

				// Clear stale analysis when item changes
				if (frm.doc.items && frm.doc.items.length > 0) {
					frm.set_value("items", []);
					frm.set_value("conversion_strategy", "");
					frm.set_value("has_transactions", 0);
					frm.set_value("has_open_quantities", 0);
					frm.set_value("total_items", 0);
				}
			});
	},

	selection_mode: function (frm) {
		frm.trigger("clear_analysis");
	},

	filter_item_group: function (frm) { frm.trigger("clear_analysis"); },
	filter_brand: function (frm) { frm.trigger("clear_analysis"); },
	filter_current_stock_uom: function (frm) {
		if (frm.doc.filter_current_stock_uom) {
			frm.set_value("current_stock_uom", frm.doc.filter_current_stock_uom);
		}
		frm.trigger("clear_analysis");
	},
	filter_item_type: function (frm) { frm.trigger("clear_analysis"); },
	filter_has_variants: function (frm) { frm.trigger("clear_analysis"); },
	filter_disabled: function (frm) { frm.trigger("clear_analysis"); },

	clear_analysis: function (frm) {
		if (frm.doc.items && frm.doc.items.length > 0) {
			frm.set_value("items", []);
			frm.set_value("conversion_strategy", "");
			frm.set_value("has_transactions", 0);
			frm.set_value("has_open_quantities", 0);
			frm.set_value("total_items", 0);
		}
	},

	new_stock_uom: function (frm) {
		if (
			frm.doc.current_stock_uom &&
			frm.doc.new_stock_uom &&
			frm.doc.current_stock_uom === frm.doc.new_stock_uom
		) {
			frappe.msgprint({
				title: __("Invalid UOM"),
				message: __(
					"New Stock UOM must be different from Current Stock UOM."
				),
				indicator: "orange",
			});
			frm.set_value("new_stock_uom", "");
			return;
		}

		// Clear stale analysis when UOM changes
		frm.trigger("clear_analysis");
	},

	before_submit: function (frm) {
		if (!frm.doc.items || frm.doc.items.length === 0) {
			frappe.validated = false;
			frappe.throw(
				__(
					"Please click Analyze first to preview affected items before submitting."
				)
			);
			return;
		}

		let direct_count = 0;
		let duplicate_count = 0;

		(frm.doc.items || []).forEach((d) => {
			if (d.strategy === "Direct") direct_count++;
			if (d.strategy === "Duplicate & Disable") duplicate_count++;
		});

		let summary_parts = [];
		if (direct_count > 0) {
			summary_parts.push(
				`<span class="text-success"><b>${direct_count}</b> item(s) will have UOM changed directly</span>`
			);
		}
		if (duplicate_count > 0) {
			summary_parts.push(
				`<span class="text-warning"><b>${duplicate_count}</b> item(s) will be duplicated &amp; the originals disabled</span>`
			);
		}

		frappe.confirm(
			`<div style="line-height: 2;">
				<p><b>${__("Confirm Stock UOM Conversion")}</b></p>
				<p>${__("This action cannot be undone. The following changes will be made:")}</p>
				<ul style="list-style: disc; padding-left: 20px;">
					${summary_parts.map((s) => `<li>${s}</li>`).join("")}
				</ul>
				<p class="text-muted">${__("All changes are logged for audit purposes.")}</p>
			</div>`,
			() => {},
			() => {
				frappe.validated = false;
			}
		);
	},

	after_submit: function (frm) {
		let failed = (frm.doc.items || []).filter(
			(d) => d.status === "Failed"
		).length;
		let converted = (frm.doc.items || []).filter(
			(d) => d.status === "Converted"
		).length;

		if (failed > 0) {
			frappe.msgprint({
				title: __("Conversion Completed with Errors"),
				message: __(
					"{0} item(s) converted, {1} item(s) failed. Check the Conversion Log for details.",
					[converted, failed]
				),
				indicator: "orange",
			});
		} else {
			frappe.msgprint({
				title: __("Conversion Successful"),
				message: __(
					"All {0} item(s) have been converted successfully.",
					[converted]
				),
				indicator: "green",
			});
		}
	},
});
