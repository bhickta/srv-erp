frappe.pages['oem-catalog'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('OEM Catalog'), single_column: true});
    const root = $('<div class="oem-stack">').appendTo(page.body);
    const context = {}, controls = {};
    const current_context = () => { Object.entries(controls).forEach(([key, control]) => { context[key] = control.get_value() || null; }); return {...context}; };
    const scope_brand = async () => {
        const brands = await srv_erp.oem.customer_brands(controls.customer.get_value(), controls.company.get_value());
        controls.brand.df.get_query = () => srv_erp.oem.brand_query(brands);
        const current = controls.brand.get_value();
        if (brands !== null && !brands.some(brand => brand.value === current)) {
            const preferred = brands.find(brand => brand.default) || (brands.length === 1 ? brands[0] : null);
            controls.brand.set_value(preferred ? preferred.value : '');
        }
        controls.brand.refresh();
        if (brands !== null && !brands.length) frappe.show_alert({message: __('No authorized brand for this customer. A manager must add an OEM Customer Brand association.'), indicator: 'orange'});
    };
    [['customer', 'Customer'], ['company', 'Company'], ['brand', 'Brand']].forEach(([field, type]) => {
        const input = frappe.ui.form.make_control({parent: $('<div>').appendTo(root), df: {fieldname: field, label: __(type), fieldtype: 'Link', options: type,
            onchange: () => { context[field] = input.get_value(); if (field !== 'brand') scope_brand(); }}, render_input: true});
        controls[field] = input;
    });
    const actions = $('<div class="oem-actions">').appendTo(root);
    $('<button type="button" class="btn btn-primary">').text(__('Find and configure products')).on('click', () => new srv_erp.oem.Configurator(current_context(), {adapter: 'standalone'}, result => frappe.msgprint(result.item_code ? `${__('Stock Item')}: ${result.item_code}` : `${__('Request saved')}: ${result.request}`))).appendTo(actions);
    const requests = $('<div class="oem-stack" aria-live="polite">').appendTo(root);
    $('<button type="button" class="btn btn-default">').text(__('Saved pending orders')).on('click', async () => {
        requests.text(__('Loading…'));
        try {
            const result = await srv_erp.oem.call('get_saved_orders'); requests.empty();
            result.orders.forEach(order => $('<button type="button" class="oem-line-card btn btn-default">').text(`${order.name} · ${order.customer} · ${order.oem_configuration_status}`).on('click', () => frappe.set_route('Form', 'Sales Order', order.name)).appendTo(requests));
        } catch (error) { requests.text(__('Unable to load saved orders.')); }
    }).appendTo(actions);
    $('<button type="button" class="btn btn-default">').text(__('My configuration drafts')).on('click', async () => {
        const result = await srv_erp.oem.call('get_saved_drafts'); requests.empty();
        result.drafts.forEach(draft => $('<button type="button" class="oem-line-card btn btn-default">').text(`${__('Resume draft')}: ${draft.name}`).on('click', () => {
            const configuration = new srv_erp.oem.Configurator(JSON.parse(draft.context_json), {adapter: 'standalone'}, result => frappe.msgprint(result.item_code || result.request), JSON.parse(draft.values_json));
            configuration.configure(draft.product);
        }).appendTo(requests));
    }).appendTo(actions);
    $('<button type="button" class="btn btn-default">').text(__('Customer assortment')).on('click', async () => {
        const result = await srv_erp.oem.call('get_customer_assortment', {context: current_context()}); requests.empty();
        result.assortment.forEach(item => $('<button type="button" class="oem-line-card btn btn-default">').text(item.display_name || item.physical_summary).on('click', () => {
            const configuration = new srv_erp.oem.Configurator(current_context(), {adapter: 'standalone'}, result => frappe.msgprint(result.item_code || result.request), item.values);
            configuration.configure(item.product);
        }).appendTo(requests));
    }).appendTo(actions);

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
