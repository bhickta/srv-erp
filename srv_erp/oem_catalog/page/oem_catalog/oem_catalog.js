frappe.pages['oem-catalog'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('OEM Catalog'), single_column: true});
    const root = $('<div class="oem-stack">').appendTo(page.body);
    const context = {};
    [['customer', 'Customer'], ['company', 'Company'], ['brand', 'Brand']].forEach(([field, type]) => {
        const input = frappe.ui.form.make_control({parent: $('<div>').appendTo(root), df: {fieldname: field, label: __(type), fieldtype: 'Link', options: type,
            onchange: () => { context[field] = input.get_value(); }}, render_input: true});
    });
    const actions = $('<div class="oem-actions">').appendTo(root);
    $('<button type="button" class="btn btn-primary">').text(__('Find and configure products')).on('click', () => new srv_erp.oem.Configurator(context, {adapter: 'standalone'}, result => frappe.msgprint(result.item_code ? `${__('Stock Item')}: ${result.item_code}` : `${__('Request saved')}: ${result.request}`))).appendTo(actions);
    const requests = $('<div class="oem-stack" aria-live="polite">').appendTo(root);
    async function render(approvals) {
        requests.text(__('Loading…'));
        try {
            const result = await srv_erp.oem.call(approvals ? 'get_approvals' : 'get_my_requests');
            requests.empty();
            result.requests.forEach(row => {
                const card = $('<div class="oem-line-card">').append($('<strong>').text(row.request), $('<span>').text(row.status || __('Pending'))).appendTo(requests);
                if (row.snapshot) Object.entries(row.snapshot.values).forEach(([key, value]) => card.append($('<div>').text(`${key}: ${value}`)));
                if (approvals) ['approve_request', 'reject_request'].forEach(method => {
                    const button = $('<button type="button" class="btn btn-default">').text(method === 'approve_request' ? __('Approve physical Item') : __('Reject'));
                    button.on('click', () => frappe.prompt({fieldname: 'reason', fieldtype: 'Small Text', label: __('Reason'), reqd: method === 'reject_request'}, async values => {
                        button.prop('disabled', true); row.command ||= srv_erp.oem.uuid();
                        try { await srv_erp.oem.call(method, {request: row.request, expected_modified: row.modified, reason: values.reason || '', idempotency_key: row.command}); await render(true); }
                        finally { button.prop('disabled', false); }
                    }, __('Review decision'))); card.append(button);
                });
            });
            if (!result.requests.length) requests.text(__('No requests in this view.'));
        } catch (error) { requests.text(__('Unable to load this view. Check permissions or reconnect.')); }
    }
    $('<button type="button" class="btn btn-default">').text(__('My requests')).on('click', () => render(false)).appendTo(actions);
    if (frappe.user_roles.includes('OEM Catalog Approver')) $('<button type="button" class="btn btn-default">').text(__('Approvals')).on('click', () => render(true)).appendTo(actions);
    if (frappe.user_roles.includes('OEM Catalog Manager')) $('<button type="button" class="btn btn-default">').text(__('Catalogue administration')).on('click', () => srv_erp.oem.admin_menu()).appendTo(actions);
};
