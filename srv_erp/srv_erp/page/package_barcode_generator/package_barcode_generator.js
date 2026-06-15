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
				},
				{
					fieldtype: "Section Break",
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
	}

	set_uom_options() {
		const item_code = this.form.get_value("item_code");
		this.form.set_value("uom", "");
		this.form.get_field("uom").df.options = "";
		this.form.get_field("uom").refresh();

		if (!item_code) {
			return;
		}

		frappe.call({
			method: "srv_erp.package_barcode.api.get_item_uoms",
			args: { item_code },
			callback: (r) => {
				const details = r.message || {};
				const uoms = details.uoms || [];
				this.form.get_field("uom").df.options = uoms.join("\n");
				this.form.get_field("uom").refresh();
				if (details.stock_uom && uoms.includes(details.stock_uom)) {
					this.form.set_value("uom", details.stock_uom);
				}
			},
		});
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
