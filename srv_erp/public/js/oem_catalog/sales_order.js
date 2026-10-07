frappe.provide('srv_erp.oem');
function oem_order_context(frm) {
    return {customer: frm.doc.customer, company: frm.doc.company, brand: frm.doc.brand_filter};
}
async function oem_apply(frm, pending) {
    if (pending._oem_applying) return;
    pending._oem_applying = true;
    try {
        const dto = await srv_erp.oem.call('validate_apply', {source: pending.request_source,
            document_context: {...oem_order_context(frm), document: frm.is_new() ? null : frm.doc.name, modified: frm.doc.modified}, row_intent_id: pending.row_intent_id});
        let row = frm.doc.items.find(r => r.oem_row_intent_id === pending.row_intent_id);
        if (!row) row = frm.add_child('items');
        await frappe.model.set_value(row.doctype, row.name, 'item_code', dto.item_code);
        await frappe.model.set_value(row.doctype, row.name, 'uom', pending.proposed_uom);
        await frappe.model.set_value(row.doctype, row.name, {qty: Number(pending.proposed_qty), delivery_date: pending.delivery_date,
            ...dto, warehouse: pending.warehouse || row.warehouse});
        pending.status = 'Applied'; pending.applied_sales_order_row = row.name;
        frm.dirty(); frm.refresh_field('items'); frm.refresh_field('oem_pending_lines');
        frappe.show_alert({message: __('Item applied. Confirm pricing and save the order.'), indicator: 'blue'});
    } finally { pending._oem_applying = false; }
}
function oem_edit_line(frm, row, pending) {
    const fields = [
        {fieldname: 'qty', label: __('Quantity'), fieldtype: 'Float', reqd: 1, default: pending ? Number(row.proposed_qty) : row.qty},
        {fieldname: 'delivery_date', label: __('Delivery date'), fieldtype: 'Date', reqd: 1, default: row.delivery_date},
        {fieldname: 'warehouse', label: __('Warehouse'), fieldtype: 'Link', options: 'Warehouse', default: row.warehouse},
        {fieldname: 'rate', label: pending ? __('Estimated unit rate') : __('Unit rate'), fieldtype: 'Currency', default: pending ? row.estimated_unit_rate : row.rate},
        {fieldname: 'notes', label: __('Notes'), fieldtype: 'Small Text', default: pending ? row.commercial_notes : row.description},
    ];
    const dialog = new frappe.ui.Dialog({title: pending ? __('Pending configuration line') : __('Order line'), fields,
        primary_action_label: __('Apply line edits'), primary_action: async values => {
            if (pending) Object.assign(row, {proposed_qty: String(values.qty), delivery_date: values.delivery_date, warehouse: values.warehouse,
                estimated_unit_rate: values.rate, commercial_notes: values.notes});
            else await frappe.model.set_value(row.doctype, row.name, {qty: values.qty, delivery_date: values.delivery_date, warehouse: values.warehouse, rate: values.rate, description: values.notes});
            frm.dirty(); dialog.hide(); oem_render_lines(frm);
        }});
    dialog.$wrapper.addClass('oem-config-dialog'); dialog.show();
}
function oem_render_lines(frm) {
    const field = frm.fields_dict.oem_line_cards;
    if (!field) return;
    const root = field.$wrapper.empty().append($('<div class="oem-stack">'));
    const stack = root.children().first();
    stack.append($('<p>').text(frm.doc.oem_unresolved_line_count ? __('Incomplete order: pending estimates are separate from official ERPNext totals.') : __('OEM order lines')));
    frm.doc.items.forEach(row => {
        const card = $('<div class="oem-line-card">').append($('<strong>').text(row.item_name || row.item_code), $('<span>').text(`${row.qty} ${row.uom} · ${row.rate || 0}`)).appendTo(stack);
        $('<button type="button" class="btn btn-default">').text(__('Edit line')).on('click', () => oem_edit_line(frm, row, false)).appendTo(card);
    });
    (frm.doc.oem_pending_lines || []).filter(r => r.status !== 'Applied').forEach(row => {
        const card = $('<div class="oem-line-card">').append($('<strong>').text(row.physical_summary || row.product), $('<span>').text(`${row.status} · ${row.proposed_qty} ${row.proposed_uom} · ${__('Estimate')}: ${row.estimated_unit_rate || 0}`)).appendTo(stack);
        if (row.status !== 'Withdrawn') {
            $('<button type="button" class="btn btn-default">').text(__('Edit intent')).on('click', () => oem_edit_line(frm, row, true)).appendTo(card);
            $('<button type="button" class="btn btn-default">').text(__('Refresh approval / Apply')).on('click', async () => {
                const status = await srv_erp.oem.call('get_request_status', {request: row.configuration_request});
                if (status.status === 'Approved') await oem_apply(frm, row);
                else frappe.msgprint(`${__('Request status')}: ${status.status}`);
                oem_render_lines(frm);
            }).appendTo(card);
            $('<button type="button" class="btn btn-default">').text(__('Withdraw line')).on('click', () => frappe.prompt({fieldname: 'reason', fieldtype: 'Small Text', label: __('Withdrawal reason'), reqd: 1}, values => {
                row.status = 'Withdrawn'; row.withdrawal_reason = values.reason; frm.dirty(); oem_render_lines(frm);
            })).appendTo(card);
        }
    });
    const pending = (frm.doc.oem_pending_lines || []).some(r => !['Applied', 'Withdrawn'].includes(r.status));
    frm.set_df_property('items', 'reqd', !(!frm.doc.docstatus && !frm.doc.items.length && pending));
}
frappe.ui.form.on('Sales Order', {
    async refresh(frm) {
        const settings = await srv_erp.oem.call('get_ui_settings');
        if (!settings.sales_order && !frm.doc.oem_pending_lines?.length) return;
        frm.set_df_property('oem_line_cards', 'hidden', false);
        oem_render_lines(frm);
        if (frm.doc.docstatus) return;
        if (settings.sales_order) frm.add_custom_button(__('Configure OEM Item'), () => {
            if (!frm.doc.customer || !frm.doc.company || !frm.doc.brand_filter) { frappe.msgprint(__('Choose Customer, Company and Brand first.')); return; }
            const intent = srv_erp.oem.uuid();
            new srv_erp.oem.Configurator(oem_order_context(frm), {adapter: 'sales_order', doctype: 'Sales Order', field: 'items', document: frm.is_new() ? null : frm.doc.name, modified: frm.doc.modified, row_intent_id: intent}, async (result, payload, preview) => {
                frm.doc.oem_order_entry_enabled = 1;
                if (result.outcome === 'EXISTING') {
                    const row = frm.add_child('items');
                    await frappe.model.set_value(row.doctype, row.name, 'item_code', result.item_code);
                    await frappe.model.set_value(row.doctype, row.name, {oem_specification: result.specification, oem_row_intent_id: intent, qty: 1});
                } else {
                    const row = frm.add_child('oem_pending_lines', {row_intent_id: result.row_intent_id, product: payload.product,
                        product_revision: result.snapshot.revision, specification: result.specification, configuration_request: result.request,
                        request_source: result.source, configuration_snapshot_json: JSON.stringify(result.snapshot), physical_summary: preview.summary,
                        proposed_qty: '1', proposed_uom: result.snapshot.package.uom, proposed_package_code: payload.package_choice,
                        delivery_date: frm.doc.delivery_date, status: 'Pending'});
                    oem_edit_line(frm, row, true);
                }
                frm.dirty(); frm.refresh_field('items'); frm.refresh_field('oem_pending_lines'); oem_render_lines(frm);
            });
        });
        frm.add_custom_button(__('Save pending SO'), () => frm.save());
    },
    validate(frm) { oem_render_lines(frm); },
});
