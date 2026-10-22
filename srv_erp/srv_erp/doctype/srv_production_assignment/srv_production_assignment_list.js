frappe.listview_settings["SRV Production Assignment"] = {
	filters: [
		[
			"status",
			"not in",
			frappe.meta
				.get_docfield("SRV Production Assignment", "status")
				.options.split("\n")
				.filter((status) => ["Cancelled", "Rejected", "Disabled"].includes(status)),
		],
	],
	onload(listview) {
		const get_field = (fieldname) => frappe.meta.get_docfield(listview.doctype, fieldname);
		const get_subject_text = listview.get_subject_text.bind(listview);
		listview.link_field_title_fields.item_code = "item_name";
		listview.link_field_title_fields.template = "item_name";

		listview.columns = [
			{ type: "Subject", df: get_field("item_name") },
			{ type: "Field", df: get_field("status") },
			{ type: "Field", df: get_field("target_qty") },
			{ type: "Field", df: get_field("percent_completed") },
		];
		listview.get_subject_text = (doc, title) => {
			const item_name =
				doc.item_name ||
				doc.item_code_item_name ||
				doc.template_item_name ||
				(title && title !== doc.name ? title : "") ||
				__("Item unavailable");

			return get_subject_text(doc, item_name);
		};
		listview.render_header(true);

		// Apply the default to existing empty saved views too. Explicit history
		// filters and filters removed during this visit remain under user control.
		if (
			!listview.filter_area
				.get()
				.some((filter) => ["status", "docstatus"].includes(filter[1]))
		) {
			return listview.filter_area.add(
				frappe.listview_settings[listview.doctype].filters.map((filter) => [
					listview.doctype,
					...filter,
				]),
			);
		}
	},
	add_fields: [
		"status",
		"planned_date",
		"item_code",
		"template",
		"item_name",
		"target_qty",
		"percent_completed",
		"uom",
	],
	hide_name_column: true,
	formatters: {
		item_name(value, df, doc) {
			return (
				doc.item_name ||
				doc.item_code_item_name ||
				doc.template_item_name ||
				(value && value !== doc.name ? value : "") ||
				__("Item unavailable")
			);
		},
		target_qty(value, df, doc) {
			const formatted_qty = frappe.format(value, df, null, doc);
			const qty = frappe.utils.escape_html(String(value ?? ""));
			const uom = frappe.utils.escape_html(doc.uom || "");

			return `<a class="filterable ellipsis" data-filter="target_qty,=,${qty}" title="${__(
				"Target Qty"
			)}: ${qty} ${uom}">${formatted_qty} ${uom}</a>`;
		},
		percent_completed(value, df, doc) {
			const percent = Number(value) || 0;
			const progress_value = Math.min(Math.max(percent, 0), 100);
			const formatted_percent = frappe.format(value, df, null, doc);

			return `
				<div class="srv-production-assignment-progress" title="${__("Produced")}: ${formatted_percent}">
					<div class="progress" role="progressbar" aria-valuenow="${progress_value}"
						aria-valuemin="0" aria-valuemax="100" aria-label="${__("Produced")}">
						<div class="progress-bar progress-bar-success" style="width: ${progress_value}%;"></div>
					</div>
					<span>${formatted_percent}</span>
				</div>
			`;
		},
	},
	get_indicator(doc) {
		if (
			doc.status !== "Completed" &&
			doc.status !== "Cancelled" &&
			doc.planned_date < frappe.datetime.get_today()
		) {
			return [
				__("{0} (Overdue)", [__(doc.status)]),
				"red",
				"planned_date,<,Today|status,not in,Completed,Cancelled",
			];
		}
		return [
			__(doc.status),
			{ Completed: "green", "In Progress": "orange", Cancelled: "gray" }[doc.status] ||
				"blue",
			`status,=,${doc.status}`,
		];
	},
};
