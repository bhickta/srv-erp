frappe.pages["zero-stock-reconciliation"].on_page_load = function (wrapper) {
	new srv_erp.stock_zeroing.ZeroStockReconciliationPage(wrapper);
};

frappe.provide("srv_erp.stock_zeroing");

srv_erp.stock_zeroing.ZeroStockReconciliationPage = class ZeroStockReconciliationPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Zero Stock Reconciliation"),
			single_column: true,
		});
		this.make();
		this.load_defaults();
	}

	make() {
		this.$body = $(`
			<div class="zero-stock-reconciliation">
				<div class="frappe-card zero-stock-reconciliation__filters"></div>
				<div class="zero-stock-reconciliation__result"></div>
			</div>
		`).appendTo(this.page.body);

		this.form = new frappe.ui.FieldGroup({
			fields: [
				{
					fieldtype: "Link",
					fieldname: "company",
					label: __("Company"),
					options: "Company",
					reqd: 1,
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Date",
					fieldname: "posting_date",
					label: __("Posting Date"),
					reqd: 1,
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Time",
					fieldname: "posting_time",
					label: __("Posting Time"),
					reqd: 1,
				},
				{
					fieldtype: "Section Break",
				},
				{
					fieldtype: "Link",
					fieldname: "warehouse",
					label: __("Warehouse"),
					options: "Warehouse",
					description: __("Blank means all leaf warehouses for the selected company."),
					get_query: () => ({
						filters: {
							company: this.form.get_value("company"),
						},
					}),
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Link",
					fieldname: "item_group",
					label: __("Item Group"),
					options: "Item Group",
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Link",
					fieldname: "item_code",
					label: __("Item"),
					options: "Item",
					get_query: () => ({
						filters: {
							is_stock_item: 1,
							disabled: 0,
						},
					}),
				},
				{
					fieldtype: "Section Break",
				},
				{
					fieldtype: "Check",
					fieldname: "include_negative_stock",
					label: __("Include Negative Stock"),
					default: 1,
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Check",
					fieldname: "include_serial_batch_items",
					label: __("Include Serial/Batch Items"),
					default: 1,
				},
				{
					fieldtype: "Column Break",
				},
				{
					fieldtype: "Int",
					fieldname: "max_rows",
					label: __("Max Rows"),
					default: 500,
				},
			],
			body: this.$body.find(".zero-stock-reconciliation__filters"),
		});
		this.form.make();

		this.page.set_primary_action(__("Preview"), () => this.preview(), "search");
		this.page.add_inner_button(__("Create Draft Stock Reconciliation"), () => this.create_reconciliation());
	}

	load_defaults() {
		frappe.call({
			method: "srv_erp.stock_zeroing.get_zero_stock_defaults",
			callback: (r) => {
				this.form.set_values(r.message || {});
				this.preview();
			},
		});
	}

	get_values() {
		return this.form.get_values();
	}

	preview() {
		const filters = this.get_values();
		if (!filters) {
			return;
		}

		frappe.call({
			method: "srv_erp.stock_zeroing.preview_zero_stock_reconciliation",
			args: { filters },
			freeze: true,
			freeze_message: __("Checking stock balances..."),
			callback: (r) => this.render_result(r.message || {}),
		});
	}

	create_reconciliation() {
		const filters = this.get_values();
		if (!filters) {
			return;
		}

		frappe.confirm(
			__(
				"Create a draft Stock Reconciliation that sets every previewed item/warehouse balance to zero?"
			),
			() => {
				frappe.call({
					method: "srv_erp.stock_zeroing.create_zero_stock_reconciliation",
					args: { filters },
					freeze: true,
					freeze_message: __("Creating Stock Reconciliation..."),
					callback: (r) => {
						const result = r.message || {};
						if (!result.name) {
							return;
						}
						frappe.show_alert({
							message: __("Draft Stock Reconciliation {0} created", [result.name]),
							indicator: "green",
						});
						frappe.set_route("Form", "Stock Reconciliation", result.name);
					},
				});
			}
		);
	}

	render_result(result) {
		const rows = result.rows || [];
		const summary = result.summary || {};
		const warning = result.truncated
			? `<div class="alert alert-warning">${__(
					"Preview is limited by Max Rows. Narrow filters before creating if this is not the intended complete set."
				)}</div>`
			: "";

		this.$body.find(".zero-stock-reconciliation__result").html(`
			${warning}
			<div class="zero-stock-reconciliation__summary">
				${this.summary_item(__("Rows"), summary.row_count || 0)}
				${this.summary_item(__("Total Qty to Clear"), flt(summary.total_abs_qty || 0))}
				${this.summary_item(__("Positive"), summary.positive_rows || 0)}
				${this.summary_item(__("Negative"), summary.negative_rows || 0)}
				${this.summary_item(__("Serial/Batch"), summary.serial_batch_rows || 0)}
			</div>
			<div class="frappe-card zero-stock-reconciliation__table">
				${this.render_table(rows)}
			</div>
		`);
	}

	summary_item(label, value) {
		return `
			<div class="zero-stock-reconciliation__summary-item">
				<div class="text-muted small">${label}</div>
				<div class="h5 mb-0">${frappe.utils.escape_html(String(value))}</div>
			</div>
		`;
	}

	render_table(rows) {
		if (!rows.length) {
			return `<div class="text-muted">${__("No non-zero stock found for these filters.")}</div>`;
		}

		const body = rows
			.map(
				(row) => `
					<tr>
						<td>${frappe.utils.escape_html(row.warehouse || "")}</td>
						<td>${frappe.utils.escape_html(row.item_code || "")}</td>
						<td>${frappe.utils.escape_html(row.item_name || "")}</td>
						<td class="text-right">${flt(row.qty)}</td>
						<td>${frappe.utils.escape_html(row.stock_uom || "")}</td>
						<td class="text-right">${flt(row.valuation_rate)}</td>
						<td>${row.has_serial_no || row.has_batch_no ? __("Yes") : __("No")}</td>
					</tr>
				`
			)
			.join("");

		return `
			<div class="table-responsive">
				<table class="table table-bordered table-hover">
					<thead>
						<tr>
							<th>${__("Warehouse")}</th>
							<th>${__("Item")}</th>
							<th>${__("Item Name")}</th>
							<th class="text-right">${__("Current Qty")}</th>
							<th>${__("UOM")}</th>
							<th class="text-right">${__("Valuation Rate")}</th>
							<th>${__("Serial/Batch")}</th>
						</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`;
	}
};

frappe.dom.set_style(`
	.zero-stock-reconciliation {
		max-width: 1280px;
	}
	.zero-stock-reconciliation__filters {
		margin-bottom: 14px;
		padding: 16px;
	}
	.zero-stock-reconciliation__summary {
		display: grid;
		gap: 0;
		grid-template-columns: repeat(5, minmax(0, 1fr));
		margin-bottom: 14px;
	}
	.zero-stock-reconciliation__summary-item {
		background: var(--control-bg);
		border: 1px solid var(--border-color);
		border-right: 0;
		min-width: 0;
		padding: 10px 12px;
	}
	.zero-stock-reconciliation__summary-item:last-child {
		border-right: 1px solid var(--border-color);
	}
	.zero-stock-reconciliation__table {
		padding: 12px;
	}
	@media (max-width: 991px) {
		.zero-stock-reconciliation__summary {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.zero-stock-reconciliation__summary-item {
			border-right: 1px solid var(--border-color);
		}
	}
`);
