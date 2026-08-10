frappe.pages["tally-export"].on_page_load = function (wrapper) {
	new srv_erp.tally_export.TallyExportPage(wrapper);
};

frappe.provide("srv_erp.tally_export");

srv_erp.tally_export.TallyExportPage = class TallyExportPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Tally Export"),
			single_column: true,
		});
		this.doctypes = [
			"Account",
			"Customer",
			"Supplier",
			"Cost Center",
			"UOM",
			"Item Group",
			"Warehouse",
			"Item",
		];
		this.make();
	}

	make() {
		this.$body = $(
			`<div class="tally-export-page">
				<div class="row">
					<div class="col-lg-8">
						<div class="frappe-card tally-export-card">
							<div class="tally-export-form"></div>
						</div>
					</div>
					<div class="col-lg-4">
						<div class="frappe-card tally-export-help">
							<h4>${__("TallyPrime Masters")}</h4>
							<p>${__("Creates native UTF-16 JSON for TallyPrime 7.0 or later.")}</p>
							<ol>
								<li>${__("Back up the target Tally company.")}</li>
								<li>${__("Open Alt+O > Import > Masters.")}</li>
								<li>${__("Select JSON and import this file.")}</li>
								<li>${__("Review Tally's Exceptions report.")}</li>
							</ol>
							<div class="alert alert-warning">
								${__("This version exports masters only. It does not export invoices or vouchers.")}
							</div>
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
					onchange: () => this.load_summary(),
				},
				{ fieldtype: "Section Break", label: __("Masters to Export") },
				...this.doctypes.flatMap((doctype, index) => {
					const fields = [];
					if (index && index % 2 === 0) {
						fields.push({ fieldtype: "Section Break" });
					} else if (index % 2 === 1) {
						fields.push({ fieldtype: "Column Break" });
					}
					fields.push({
						fieldtype: "Check",
						fieldname: frappe.scrub(doctype),
						label: __(doctype),
						default: 1,
					});
					return fields;
				}),
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "summary" },
			],
			body: this.$body.find(".tally-export-form"),
		});
		this.form.make();
		this.page.set_primary_action(__("Download Masters JSON"), () => this.download(), "download");
		this.load_summary();
	}

	get_selected_doctypes() {
		return this.doctypes.filter((doctype) => this.form.get_value(frappe.scrub(doctype)));
	}

	load_summary() {
		const company = this.form?.get_value("company");
		if (!company) {
			this.render_summary({});
			return;
		}
		frappe.call({
			method: "srv_erp.integrations.tally_export.get_export_summary",
			args: { company },
			callback: (r) => this.render_summary(r.message || {}),
		});
	}

	render_summary(summary) {
		const rows = this.doctypes
			.map(
				(doctype) => `<tr><td>${__(doctype)}</td><td class="text-right">${format_number(
					summary[doctype] || 0,
				)}</td></tr>`,
			)
			.join("");
		this.form.get_field("summary").$wrapper.html(`
			<h5>${__("Available records")}</h5>
			<table class="table table-bordered table-sm"><tbody>${rows}</tbody></table>
		`);
	}

	download() {
		const values = this.form.get_values();
		if (!values) {
			return;
		}
		const doctypes = this.get_selected_doctypes();
		if (!doctypes.length) {
			frappe.msgprint(__("Select at least one master type."));
			return;
		}
		const params = new URLSearchParams({
			company: values.company,
			doctypes: JSON.stringify(doctypes),
		});
		window.open(`/api/method/srv_erp.integrations.tally_export.download_master_json?${params}`, "_blank");
	}
};

frappe.dom.set_style(`
	.tally-export-card, .tally-export-help { padding: 20px; }
	.tally-export-help ol { padding-left: 20px; }
	.tally-export-help .alert { margin-bottom: 0; margin-top: 18px; }
`);
