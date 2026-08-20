frappe.pages["tally-export"].on_page_load = function (wrapper) {
	new srv_erp.tally_export.TallyExportPage(wrapper);
};

frappe.provide("srv_erp.tally_export");

srv_erp.tally_export.TallyExportPage = class TallyExportPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Tally Sales Order Export"),
			single_column: true,
		});
		this.make();
	}

	make() {
		this.$body = $(
			`<div class="tally-export-page">
				<div class="row">
					<div class="col-lg-8">
						<div class="frappe-card tally-export-card"><div class="tally-export-form"></div></div>
					</div>
					<div class="col-lg-4">
						<div class="frappe-card tally-export-help">
							<h4>${__("Import into Tally")}</h4>
							<p>${__("Downloads native UTF-16 JSON for TallyPrime 7.0 or later.")}</p>
							<ol>
								<li>${__("Download Required Masters, then import it from Alt+O > Import > Masters.")}</li>
								<li>${__("Enable Sales Order processing in TallyPrime.")}</li>
								<li>${__("Download Sales Orders, then import it from Alt+O > Import > Transactions.")}</li>
								<li>${__("Review Tally's import summary and Exceptions.")}</li>
							</ol>
							<div class="alert alert-info">${__("Always import the generated Masters file first. It contains the exact items and dependencies used by the selected orders.")}</div>
						</div>
					</div>
				</div>
			</div>`,
		).appendTo(this.page.body);

		this.form = new frappe.ui.FieldGroup({
			fields: [
				{
					fieldtype: "Link",
					fieldname: "company",
					label: __("Company"),
					options: "Company",
					default: frappe.defaults.get_user_default("Company"),
					reqd: 1,
					onchange: () => this.load_count(),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Link",
					fieldname: "customer",
					label: __("Customer"),
					options: "Customer",
					onchange: () => this.load_count(),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Date",
					fieldname: "from_date",
					label: __("From Date"),
					default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
					reqd: 1,
					onchange: () => this.load_count(),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Date",
					fieldname: "to_date",
					label: __("To Date"),
					default: frappe.datetime.get_today(),
					reqd: 1,
					onchange: () => this.load_count(),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Link",
					fieldname: "sales_order",
					label: __("Sales Order"),
					options: "Sales Order",
					get_query: () => ({
						filters: {
							company: this.form.get_value("company"),
							docstatus: 1,
						},
					}),
					onchange: () => this.load_count(),
				},
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "summary" },
			],
			body: this.$body.find(".tally-export-form"),
		});
		this.form.make();
		this.page.set_primary_action(__("2. Download Sales Orders"), () => this.download_sales_orders(), "download");
		this.page.add_inner_button(__("1. Download Required Masters"), () => this.download_masters());
		this.load_count();
	}

	get_values() {
		return this.form.get_values();
	}

	load_count() {
		const values = this.get_values();
		if (!values) {
			return;
		}
		frappe.call({
			method: "srv_erp.integrations.tally_export.get_sales_order_count",
			args: values,
			callback: (r) => {
				const count = r.message || 0;
				this.form.get_field("summary").$wrapper.html(
					`<div class="alert alert-info">${__("{0} submitted Sales Order(s) will be exported.", [
						format_number(count),
					])}</div>`,
				);
			},
		});
	}

	get_download_params() {
		const values = this.get_values();
		if (!values) {
			return null;
		}
		const params = new URLSearchParams();
		Object.entries(values).forEach(([key, value]) => {
			if (value) {
				params.set(key, value);
			}
		});
		return params;
	}

	download_masters() {
		const params = this.get_download_params();
		if (!params) return;
		window.open(
			`/api/method/srv_erp.integrations.tally_export.download_sales_order_masters_json?${params}`,
			"_blank",
		);
	}

	download_sales_orders() {
		const params = this.get_download_params();
		if (!params) return;
		window.open(`/api/method/srv_erp.integrations.tally_export.download_sales_order_json?${params}`, "_blank");
	}
};

frappe.dom.set_style(`
	.tally-export-card, .tally-export-help { padding: 20px; }
	.tally-export-help ol { padding-left: 20px; }
	.tally-export-help .alert { margin-bottom: 0; margin-top: 18px; }
`);
