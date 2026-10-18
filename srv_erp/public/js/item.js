frappe.provide("erpnext.item");
frappe.provide("srv_erp.item");

srv_erp.item.toggle_variant_item_group = function (frm) {
	const is_variant = Boolean(frm.doc.variant_of);
	frm.set_df_property("item_group", "read_only", is_variant ? 1 : 0);
};

frappe.ui.form.on("Item", {
	setup: srv_erp.item.toggle_variant_item_group,
	refresh(frm) {
		srv_erp.item.toggle_variant_item_group(frm);
		if (!frm.is_new() && frm.doc.variant_of && frm.doc.variant_based_on === "Item Attribute") {
			frm.toggle_enable("attributes", true);
			const grid = frm.fields_dict.attributes.grid;
			grid.toggle_enable("attribute_value", true);
			grid.toggle_enable("attribute", true);
			grid.cannot_add_rows = false;
			grid.cannot_delete_rows = true;
			grid.refresh();
		}
		if (!frm.is_new() && frm.doc.has_variants) {
			frm.add_custom_button(__("Manage Variant Prices"), () => {
				frappe.route_options = { item_code: frm.doc.name };
				frappe.set_route("List", "Item Price");
			}, __("Prices"));
		}
		if (srv_erp.dynamic_item) {
			srv_erp.dynamic_item.configure_template_item(frm);
		}
	},
	variant_of: srv_erp.item.toggle_variant_item_group,
});

frappe.ui.form.on("Item", {
	setup(frm) {
		frm.set_query("custom_production_supervisor", () => ({
			query: "srv_erp.production.service.supervisor_query",
		}));
	},
	refresh(frm) {
		if (
			!frm.is_new() &&
			(frm.doc.has_variants || frm.doc.variant_of) &&
			frappe.model.can_create("SRV Production Schedule")
		) {
			frm.add_custom_button(__("Plan Production"), () => {
				frappe.new_doc("SRV Production Schedule", {}, doc => {
					const row = frappe.model.add_child(doc, "SRV Production Schedule Item", "items");
					row.template = frm.doc.variant_of || frm.doc.name;
					row.item_code = frm.doc.variant_of ? frm.doc.name : null;
					row.qty_per_occurrence = 1;
				});
			});
		}
	},
});
