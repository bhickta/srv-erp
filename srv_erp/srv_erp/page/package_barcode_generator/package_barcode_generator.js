frappe.pages["package-barcode-generator"].on_page_load = function (wrapper) {
	new srv_erp.package_barcode.PackageBarcodeGeneratorPage(wrapper);
};

frappe.provide("srv_erp.package_barcode");

srv_erp.package_barcode.PackageBarcodeGeneratorPage = class PackageBarcodeGeneratorPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Package Barcode Generator"),
			single_column: true,
		});
		this.make();
	}

	make() {
		this.$body = $(`
			<div class="package-barcode-generator">
				<div class="row">
					<div class="col-md-8">
						<div class="frappe-card">
							<div class="package-barcode-form"></div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.form = new frappe.ui.FieldGroup({
			fields: [
				{
					fieldtype: "Link",
					fieldname: "item_code",
					label: __("Item Code"),
					options: "Item",
					reqd: 1,
					get_query: () => {
						return { filters: { is_stock_item: 1, disabled: 0 } };
					},
					onchange: () => this.set_uom_options(),
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Select",
					fieldname: "uom",
					label: __("UOM"),
					reqd: 1,
					onchange: () => this.render_preview(),
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Int",
					fieldname: "no_of_barcodes",
					label: __("No. of Barcodes"),
					reqd: 1,
					default: 1,
					onchange: () => this.render_preview(),
				},
				{
					fieldtype: "Section Break",
				},
				{
					fieldtype: "HTML",
					fieldname: "preview",
				},
				{
					fieldtype: "HTML",
					fieldname: "result",
				},
			],
			body: this.$body.find(".package-barcode-form"),
		});
		this.form.make();

		this.page.set_primary_action(__("Generate Excel"), () => this.generate(), "download");
		this.item_details = null;
		this.render_preview();
	}

	set_uom_options() {
		const item_code = this.form.get_value("item_code");
		this.item_details = null;
		this.form.set_value("uom", "");
		this.form.get_field("uom").df.options = "";
		this.form.get_field("uom").refresh();
		this.render_preview();

		if (!item_code) {
			return;
		}

		frappe.call({
			method: "srv_erp.package_barcode.api.get_item_uoms",
			args: { item_code },
			callback: (r) => {
				const details = r.message || {};
				this.item_details = details;
				const uoms = details.uoms || [];
				this.form.get_field("uom").df.options = uoms.join("\n");
				this.form.get_field("uom").refresh();
				if (details.stock_uom && uoms.includes(details.stock_uom)) {
					this.form.set_value("uom", details.stock_uom);
				}
				this.render_preview();
			},
		});
	}

	render_preview() {
		const values = {
			item_code: this.form?.get_value("item_code"),
			uom: this.form?.get_value("uom"),
			no_of_barcodes: this.form?.get_value("no_of_barcodes") || 0,
		};
		const item_name = this.item_details?.item_name || "-";

		this.form.get_field("preview").$wrapper.html(`
			<div class="package-barcode-preview">
				<div class="package-barcode-preview__title">${__("Generation Preview")}</div>
				<div class="package-barcode-preview__grid">
					<div>
						<div class="text-muted small">${__("Item")}</div>
						<div class="text-truncate">${frappe.utils.escape_html(values.item_code || "-")}</div>
					</div>
					<div>
						<div class="text-muted small">${__("Item Name")}</div>
						<div class="text-truncate">${frappe.utils.escape_html(item_name)}</div>
					</div>
					<div>
						<div class="text-muted small">${__("UOM")}</div>
						<div>${frappe.utils.escape_html(values.uom || "-")}</div>
					</div>
					<div>
						<div class="text-muted small">${__("Count")}</div>
						<div>${frappe.utils.escape_html(cint(values.no_of_barcodes).toString())}</div>
					</div>
				</div>
			</div>
		`);
	}

	generate() {
		const values = this.form.get_values();
		if (!values) {
			return;
		}

		frappe.call({
			method: "srv_erp.package_barcode.api.generate_package_barcodes",
			args: values,
			freeze: true,
			freeze_message: __("Generating Package Barcodes..."),
			callback: (r) => {
				const result = r.message;
				if (!result) {
					return;
				}

				this.show_result(result);
				this.download(result.batch);
			},
		});
	}

	show_result(result) {
		this.form.get_field("result").$wrapper.html(`
			<div class="alert alert-success">
				${__("Generated {0} package barcode(s) in batch {1}.", [
					result.generated_count,
					frappe.utils.escape_html(result.batch),
				])}
			</div>
		`);
	}

	download(batch) {
		const url =
			"/api/method/srv_erp.package_barcode.api.download_package_barcode_batch?batch=" +
			encodeURIComponent(batch);
		window.open(url, "_blank");
	}
};

frappe.dom.set_style(`
	.package-barcode-preview {
		background: var(--control-bg);
		border: 1px solid var(--border-color);
		border-radius: 8px;
		margin-bottom: 12px;
		padding: 12px;
	}
	.package-barcode-preview__title {
		font-weight: 600;
		margin-bottom: 10px;
	}
	.package-barcode-preview__grid {
		display: grid;
		gap: 12px;
		grid-template-columns: repeat(4, minmax(0, 1fr));
	}
	@media (max-width: 767px) {
		.package-barcode-preview__grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
`);

// Additive guided action; the original concrete Item path remains available.
const oem_barcode_original_load = frappe.pages['package-barcode-generator'].on_page_load;
frappe.pages['package-barcode-generator'].on_page_load = function (wrapper) {
    oem_barcode_original_load(wrapper);
    srv_erp.oem.call('get_ui_settings').then(settings => {
        if (!settings.barcode) return;
        const page = wrapper.page;
        const launch = context => new srv_erp.oem.Configurator(context, {adapter: 'barcode'}, async (result, payload, preview) => {
            if (result.outcome !== 'EXISTING') { frappe.msgprint(__('Request saved. Reopen this configuration after approval to generate labels.')); return; }
            const command = srv_erp.oem.uuid();
            const dialog = new frappe.ui.Dialog({title: __('Generate OEM package labels'), fields: [
                {fieldname: 'summary', fieldtype: 'HTML', options: `<p>${srv_erp.oem.escape(preview.summary)}</p><p>${srv_erp.oem.escape(`1 ${preview.package.uom} = ${preview.package.factor} ${preview.package.stock_uom}`)}</p>`},
                {fieldname: 'count', label: __('Number of packages / labels'), fieldtype: 'Int', default: 1, reqd: 1},
                {fieldname: 'result', fieldtype: 'HTML'},
            ], primary_action_label: __('Generate'), primary_action: async values => {
                dialog.get_primary_btn().prop('disabled', true);
                try {
                    const generated = await srv_erp.oem.call('generate_barcodes', {specification: result.specification, context,
                        package_choice: payload.package_choice, count: values.count, idempotency_key: command});
                    const target = dialog.fields_dict.result.$wrapper.empty();
                    target.append($('<p>').text(`${generated.generated_count} ${__('packages')} = ${generated.stock_quantity} ${generated.stock_uom}`));
                    $('<a class="btn btn-primary">').text(__('Download Excel')).attr('href', '/api/method/srv_erp.package_barcode.api.download_package_barcode_batch?batch=' + encodeURIComponent(generated.batch)).appendTo(target);
                    dialog.get_primary_btn().hide();
                } catch (error) { dialog.fields_dict.result.$wrapper.text(__('No confirmed generation. Retry the same package count to recover the existing result.')); dialog.get_primary_btn().prop('disabled', false); }
            }});
            dialog.$wrapper.addClass('oem-config-dialog'); dialog.show();
            });
        const scope_brand = async dialog => {
            const brands = await srv_erp.oem.customer_brands(dialog.get_value('customer'), dialog.get_value('company'));
            dialog.fields_dict.brand.df.get_query = () => srv_erp.oem.brand_query(brands);
            const current = dialog.get_value('brand');
            if (brands !== null && !brands.some(brand => brand.value === current)) {
                const preferred = brands.find(brand => brand.default) || (brands.length === 1 ? brands[0] : null);
                dialog.set_value('brand', preferred ? preferred.value : '');
            }
            if (brands !== null && !brands.length) frappe.show_alert({message: __('No authorized brand for this customer. A manager must add an OEM Customer Brand association.'), indicator: 'orange'});
        };
        page.add_inner_button(__('Configure OEM Item'), () => {
            let dialog;
            dialog = new frappe.ui.Dialog({title: __('Barcode context'), fields: [
                {fieldname: 'company', label: __('Company'), fieldtype: 'Link', options: 'Company', reqd: 1, onchange: () => scope_brand(dialog)},
                {fieldname: 'customer', label: __('Customer'), fieldtype: 'Link', options: 'Customer', onchange: () => scope_brand(dialog)},
                {fieldname: 'brand', label: __('Brand'), fieldtype: 'Link', options: 'Brand', reqd: 1},
            ], primary_action_label: __('Configure'),
                primary_action(values) { dialog.hide(); launch({company: values.company, customer: values.customer, brand: values.brand}); }});
            dialog.show();
        });
    });
};
