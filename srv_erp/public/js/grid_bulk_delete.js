/* global frappe */

frappe.provide("srv_erp.grid_bulk_delete");

// Frappe deletes grid rows through a fire-and-forget async pipeline that looks each row
// up by name in grid_rows_by_docname. That map only holds the currently rendered page, and
// _remove handlers (e.g. ERPNext's items_remove -> calculate_taxes_and_totals ->
// frm.refresh_fields) rebuild the grid mid-loop. As a result bulk delete silently skips
// rows and removes a different subset on every click. Remove from the model by stable
// identity instead, and refresh once at the end.
srv_erp.grid_bulk_delete.remove_selected_rows = async function (grid) {
	const selected = grid.get_selected_children();
	if (!selected.length) {
		return;
	}

	const fieldname = grid.df.fieldname;

	if (!grid.frm) {
		const selected_names = new Set(selected.map((doc) => doc.name));
		grid.df.data = grid.get_data().filter((row) => !selected_names.has(row.name));
		grid.df.data.forEach((row, index) => (row.idx = index + 1));
		grid.refresh();
		return;
	}

	const frm = grid.frm;
	for (const doc of selected) {
		try {
			const row = grid.grid_rows_by_docname?.[doc.name];
			if (row?.get_open_form?.()) {
				row.hide_form();
			}
			await frm.script_manager.trigger("before_" + fieldname + "_remove", doc.doctype, doc.name);
			frappe.model.clear_doc(doc.doctype, doc.name);
			await frm.script_manager.trigger(fieldname + "_remove", doc.doctype, doc.name);
		} catch (error) {
			console.trace(error);
		}
	}

	frm.dirty();
	grid.refresh();
	await frm.script_manager.trigger(fieldname + "_delete", grid.doctype);

	grid.wrapper.find(".grid-heading-row .grid-row-check:checked:first").prop("checked", 0);
	if (selected.length === grid.grid_pagination.page_length) {
		grid.scroll_to_top();
	}
};

frappe.ui.form.Grid.prototype.delete_rows = function () {
	return srv_erp.grid_bulk_delete.remove_selected_rows(this);
};
