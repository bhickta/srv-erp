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
