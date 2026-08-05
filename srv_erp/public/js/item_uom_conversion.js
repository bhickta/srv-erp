/**
 * Item form extension: Stock UOM Conversion button
 *
 * Adds a "Change Stock UOM" button to the Item form that creates a new
 * Stock UOM Conversion document pre-filled with the current item.
 */
frappe.ui.form.on("Item", {
	refresh(frm) {
		srv_erp.item.add_uom_conversion_button(frm);
	},
});

frappe.provide("srv_erp.item");

srv_erp.item.add_uom_conversion_button = function (frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0) return;

	frm.add_custom_button(
		__("Change Stock UOM"),
		function () {
			srv_erp.item.open_uom_conversion_dialog(frm);
		},
		__("Actions")
	);
};

srv_erp.item.open_uom_conversion_dialog = function (frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Change Stock UOM for {0}", [frm.doc.item_code]),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info_banner",
				options: `
					<div class="alert alert-info d-flex align-items-start mb-4" style="border-radius: 8px; border-left: 4px solid var(--primary);">
						<span class="mr-2" style="font-size: 18px;">ℹ️</span>
						<div>
							<strong>${__("Non-Destructive Conversion")}</strong><br>
							<span class="text-muted">${__("If stock transactions exist, the original item will be disabled and a new item created with the correct UOM. Your transaction history is always preserved.")}</span>
						</div>
					</div>
				`,
			},
			{
				fieldtype: "Section Break",
				label: __("Current Item"),
			},
			{
				fieldname: "item_code",
				fieldtype: "Data",
				label: __("Item Code"),
				default: frm.doc.item_code,
				read_only: 1,
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldname: "current_stock_uom",
				fieldtype: "Data",
				label: __("Current Stock UOM"),
				default: frm.doc.stock_uom,
				read_only: 1,
			},
			{
				fieldtype: "Section Break",
				label: __("New UOM"),
			},
			{
				fieldname: "new_stock_uom",
				fieldtype: "Link",
				label: __("New Stock UOM"),
				options: "UOM",
				reqd: 1,
				description: __(
					"Select the new default Unit of Measure for this item."
				),
			},
			{
				fieldtype: "Section Break",
			},
			{
				fieldtype: "HTML",
				fieldname: "template_info",
				options: frm.doc.has_variants
					? `<div class="alert alert-warning" style="border-radius: 8px; border-left: 4px solid var(--yellow-500);">
						<strong>⚠️ ${__("Template Item")}</strong><br>
						<span class="text-muted">${__("This is a template item with variants. The conversion tool will also handle all variant items.")}</span>
					</div>`
					: "",
			},
		],
		primary_action_label: __("Create Conversion Request"),
		primary_action: function (values) {
			if (values.new_stock_uom === frm.doc.stock_uom) {
				frappe.msgprint({
					title: __("Same UOM"),
					message: __(
						"New Stock UOM is the same as the current one. Please select a different UOM."
					),
					indicator: "orange",
				});
				return;
			}

			dialog.hide();
			frappe.new_doc("Stock UOM Conversion", {
				item_code: frm.doc.item_code,
				current_stock_uom: frm.doc.stock_uom,
				new_stock_uom: values.new_stock_uom,
			});
		},
	});

	dialog.show();
};
