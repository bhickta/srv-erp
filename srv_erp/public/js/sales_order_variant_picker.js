/* global frappe */

const srv_variant_picker_method = "srv_erp.selling.sales_order.get_variant_picker_data";

function srv_variant_picker_escape(value) {
	return String(value || "").replace(/[&<>"']/g, (character) => ({
		"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
	})[character]);
}

function srv_variant_picker_styles() {
	if (document.getElementById("srv-variant-picker-styles")) return;
	$("<style>", { id: "srv-variant-picker-styles" }).text(`
		.srv-variant-dialog { width: min(920px, 96vw) !important; }
		.srv-variant-dialog .modal-content { border: 0; border-radius: 18px; overflow: hidden; box-shadow: 0 22px 70px #15263c30; }
		.srv-variant-dialog .modal-header { padding: 22px 28px; background: linear-gradient(110deg, #183b52, #22666a); color: white; }
		.srv-variant-dialog .modal-title, .srv-variant-dialog .close { color: white; }
		.srv-variant-dialog .modal-body { padding: 22px 28px 28px; }
		.srv-variant-dialog .form-section { border: 0; }
		.srv-variant-panel { border: 1px solid #e2e8ec; border-radius: 14px; padding: 18px; margin-top: 18px; background: #fbfcfd; }
		.srv-variant-heading { font-size: 13px; font-weight: 700; letter-spacing: .03em; color: #425466; margin: 0 0 12px; }
		.srv-variant-facet { margin: 0 0 16px; }
		.srv-variant-facet:last-child { margin-bottom: 0; }
		.srv-variant-facet-label { font-size: 12px; font-weight: 600; color: #596b79; margin-bottom: 8px; }
		.srv-variant-chips { display: flex; flex-wrap: wrap; gap: 7px; }
		.srv-variant-chip { border: 1px solid #cbd8df; border-radius: 999px; padding: 6px 12px; background: white; color: #365367; transition: background .15s, border-color .15s; }
		.srv-variant-chip:hover { border-color: #24867f; background: #eef8f5; }
		.srv-variant-chip.is-selected { color: white; background: #197b73; border-color: #197b73; }
		.srv-variant-results { display: grid; gap: 8px; max-height: 320px; overflow: auto; }
		.srv-variant-result { width: 100%; text-align: left; padding: 12px 14px; background: white; border: 1px solid #e0e8ed; border-radius: 10px; display: flex; align-items: center; justify-content: space-between; gap: 14px; }
		.srv-variant-result:hover { border-color: #197b73; background: #f4faf8; }
		.srv-variant-result strong { display: block; color: #223849; }
		.srv-variant-result small { display: block; color: #71818d; margin-top: 2px; }
		.srv-variant-result .srv-variant-select { white-space: nowrap; color: #197b73; font-weight: 600; }
		.srv-variant-empty { color: #71818d; padding: 16px 0; text-align: center; }
		.srv-variant-request { margin-top: 14px; width: 100%; border: 1px dashed #78aba7; border-radius: 10px; padding: 12px; background: #eff8f6; color: #176b65; font-weight: 600; }
		.srv-variant-request:hover { background: #e1f2ee; }
		@media (max-width: 600px) {
			.srv-variant-dialog { width: 100vw !important; max-width: 100vw !important; margin: 0 !important; }
			.srv-variant-dialog .modal-content { min-height: 100dvh; border-radius: 0; }
			.srv-variant-dialog .modal-body { padding: 16px; max-height: calc(100dvh - 74px); overflow-y: auto; }
			.srv-variant-dialog .modal-header { padding: 18px 16px; }
			.srv-variant-dialog .form-column { width: 100% !important; float: none !important; }
			.srv-variant-panel { padding: 14px; margin-top: 12px; }
			.srv-variant-chip { min-height: 42px; }
			.srv-variant-result { min-height: 58px; }
		}
	`).appendTo(document.head);
}

function srv_open_variant_picker(frm, cdt, cdn) {
	srv_variant_picker_styles();
	const selected = {};
	let request_id = 0;
	let search_timer;
	let dialog;

	const refresh = async () => {
		const current_request = ++request_id;
		const $content = dialog.fields_dict.variant_picker_content.$wrapper;
		$content.html(`<div class="srv-variant-empty">${__("Finding available variants…")}</div>`);
		try {
			const response = await frappe.call({
				method: srv_variant_picker_method,
				args: {
					brand: dialog.get_value("brand") || "",
					template: dialog.get_value("template") || "",
					attributes: selected,
					search: dialog.get_value("search") || "",
				},
			});
			if (current_request !== request_id) return;
			const data = response.message || { facets: [], items: [] };
			const facets = data.facets.map((facet) => `
				<div class="srv-variant-facet">
					<div class="srv-variant-facet-label">${srv_variant_picker_escape(facet.attribute)}</div>
					<div class="srv-variant-chips">${facet.values.map((value) => `
						<button type="button" class="srv-variant-chip ${selected[facet.attribute] === value ? "is-selected" : ""}"
							data-attribute="${srv_variant_picker_escape(facet.attribute)}" data-value="${srv_variant_picker_escape(value)}">${srv_variant_picker_escape(value)}</button>
					`).join("") || `<span class="text-muted">${__("No matching values")}</span>`}</div>
				</div>
			`).join("");
			const results = data.items.map((item) => `
				<button type="button" class="srv-variant-result" data-item="${srv_variant_picker_escape(item.name)}">
					<span><strong>${srv_variant_picker_escape(item.item_name || item.name)}</strong>
					<small>${srv_variant_picker_escape(item.name)} · ${srv_variant_picker_escape(item.variant_of)}</small></span>
					<span class="srv-variant-select">${__("Select")} →</span>
				</button>
			`).join("");
			$content.html(`
				<div class="srv-variant-panel"><div class="srv-variant-heading">${__("REFINE BY ATTRIBUTE")}</div>
					${facets || `<div class="srv-variant-empty">${__("Choose a brand or template to explore its attributes.")}</div>`}</div>
				<div class="srv-variant-panel"><div class="srv-variant-heading">${__("MATCHING VARIANTS")}</div>
					<div class="srv-variant-results">${results || `<div class="srv-variant-empty">${__("No variants match these filters.")}</div>`}</div>
					${data.has_more ? `<small class="text-muted">${__("Showing the first 30. Refine filters or search to see more.")}</small>` : ""}
					${data.can_request ? `<button type="button" class="srv-variant-request">${__("Can't find the combination? Resolve or request a variant")} →</button>` : ""}</div>
			`);
		} catch (error) {
			if (current_request === request_id) {
				$content.html(`<div class="srv-variant-empty">${__("Could not load variants. Please try again.")}</div>`);
			}
		}
	};

	dialog = new frappe.ui.Dialog({
		title: __("Find Item Variant"),
		fields: [
			{
				fieldname: "brand", fieldtype: "Link", options: "Brand", label: __("Brand"),
				default: frm.doc.brand_filter || "", read_only: Boolean(frm.doc.brand_filter),
				description: frm.doc.brand_filter ? __("Clear the Sales Order brand filter to use different brands across rows.") : "",
				onchange: () => { Object.keys(selected).forEach((key) => delete selected[key]); refresh(); },
			},
			{ fieldname: "template", fieldtype: "Link", options: "Item", label: __("Item Template"),
				get_query: () => ({ filters: { has_variants: 1, disabled: 0 } }),
				onchange: () => { Object.keys(selected).forEach((key) => delete selected[key]); refresh(); },
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "search", fieldtype: "Data", label: __("Search variants"),
				onchange: () => { clearTimeout(search_timer); search_timer = setTimeout(refresh, 250); },
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "variant_picker_content", fieldtype: "HTML" },
		],
	});
	dialog.$wrapper.find(".modal-dialog").addClass("srv-variant-dialog");
	const $content = dialog.fields_dict.variant_picker_content.$wrapper;
	$content.on("click", ".srv-variant-chip", function () {
		const attribute = $(this).attr("data-attribute");
		const value = $(this).attr("data-value");
		if (selected[attribute] === value) delete selected[attribute];
		else selected[attribute] = value;
		refresh();
	});
	$content.on("click", ".srv-variant-result", async function () {
		const item_code = $(this).attr("data-item");
		let row_cdt = cdt;
		let row_cdn = cdn;
		if (!row_cdn) {
			const row = frm.add_child("items");
			row_cdt = row.doctype;
			row_cdn = row.name;
			frm.refresh_field("items");
		}
		await frappe.model.set_value(row_cdt, row_cdn, "item_code", item_code);
		dialog.hide();
	});
	$content.on("click", ".srv-variant-request", () => {
		const template = dialog.get_value("template");
		if (!template || !window.srv_erp?.dynamic_item?.open_parameter_dialog) return;
		dialog.hide();
		const preferred = { ...selected };
		if (dialog.get_value("brand")) preferred.Brand = dialog.get_value("brand");
		srv_erp.dynamic_item.open_parameter_dialog(
			template, frm, { fieldname: "items", row_name: cdn }, preferred
		);
	});
	dialog.show();
	refresh();
}

frappe.ui.form.on("Sales Order Item", {
	srv_find_variant(frm, cdt, cdn) {
		srv_open_variant_picker(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		const grid = frm.fields_dict.items?.grid;
		if (!grid || grid.__srv_variant_picker_button) return;
		grid.__srv_variant_picker_button = true;
		grid.add_custom_button(__("Find Variant"), () => {
			const selected = grid.get_selected_children?.() || [];
			const row = selected.length === 1 && !selected[0].item_code ? selected[0] : null;
			srv_open_variant_picker(frm, row?.doctype, row?.name);
		});
	},
});
