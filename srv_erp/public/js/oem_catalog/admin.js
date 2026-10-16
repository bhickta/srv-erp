frappe.provide('srv_erp.oem');
srv_erp.oem.edit_master = async function (doctype, name = null) {
    const schema = await srv_erp.oem.call('get_admin_schema', {doctype});
    const record = name ? await srv_erp.oem.call('get_admin_record', {doctype, name}) : {};
    const fields = schema.fields.filter(f => f.fieldtype !== 'Table').map(f => ({...f, label: __(f.label), default: record[f.fieldname] ?? f.default}));
    fields.push({fieldname: 'details', fieldtype: 'HTML'});
    let key = srv_erp.oem.uuid();
    const dialog = new frappe.ui.Dialog({title: __(doctype), fields, primary_action_label: __('Save catalogue draft'), primary_action: async values => {
        dialog.get_primary_btn().prop('disabled', true);
        const payload = {...values}; delete payload.details;
        schema.fields.filter(f => f.fieldtype === 'Table').forEach(f => { payload[f.fieldname] = (record[f.fieldname] || []).map(row => Object.fromEntries(Object.entries(row).filter(([k]) => k === 'name' || f.children.some(child => child.fieldname === k)))); });
        try {
            const saved = await srv_erp.oem.call('save_catalogue_record', {doctype, name, expected_modified: record.modified, payload, idempotency_key: key});
            dialog.hide(); frappe.show_alert({message: `${__('Saved')}: ${saved.name}`, indicator: 'green'});
            srv_erp.oem.edit_master(doctype, saved.name);
        } finally { dialog.get_primary_btn().prop('disabled', false); }
    }});
    dialog.$wrapper.addClass('oem-config-dialog');
    const body = dialog.fields_dict.details.$wrapper;
    schema.fields.filter(f => f.fieldtype === 'Table').forEach(field => {
        const section = $('<div class="oem-stack">').append($('<h5>').text(__(field.label))).appendTo(body);
        function redraw() {
            section.find('.oem-detail-rows').remove();
            const cards = $('<div class="oem-detail-rows oem-stack">').appendTo(section);
            (record[field.fieldname] || []).forEach((row, index) => {
                const card = $('<div class="oem-line-card">').append($('<strong>').text(row.label || row.attribute_key || row.company || row.code || `${__('Detail')} ${index + 1}`)).appendTo(cards);
                $('<button type="button" class="btn btn-default">').text(__('Edit detail')).on('click', () => edit(row, index)).appendTo(card);
            });
        }
        function edit(row = {}, index = null) {
            const editor = new frappe.ui.Dialog({title: __(field.label), fields: field.children.map(f => ({...f, label: __(f.label), default: row[f.fieldname] ?? f.default})),
                primary_action_label: __('Keep detail'), primary_action: values => {
                    record[field.fieldname] ||= [];
                    if (index === null) record[field.fieldname].push(values);
                    else record[field.fieldname][index] = {...row, ...values};
                    key = srv_erp.oem.uuid(); editor.hide(); redraw();
                }});
            editor.$wrapper.addClass('oem-config-dialog'); editor.show();
        }
        $('<button type="button" class="btn btn-default">').text(__('Add detail')).on('click', () => edit()).appendTo(section); redraw();
    });
    if (name) {
        const actions = $('<div class="oem-actions">').appendTo(body);
        const commands = {'OEM Product Revision': ['publish_product_revision', 'revision'], 'OEM Default Profile': ['publish_default_profile', 'profile'],
            'OEM Asset Revision': ['approve_asset_revision', 'revision'], 'OEM Customer Brand': ['approve_customer_brand', 'association']};
        if (commands[doctype]) {
            const [method, field] = commands[doctype];
            $('<button type="button" class="btn btn-primary">').text(__('Publish / approve saved revision')).on('click', async function () {
                $(this).prop('disabled', true);
                try { await srv_erp.oem.call(method, {[field]: name, expected_modified: record.modified, idempotency_key: srv_erp.oem.uuid()}); dialog.hide(); }
                finally { $(this).prop('disabled', false); }
            }).appendTo(actions);
        }
    }
    dialog.show();
};
srv_erp.oem.admin_menu = function () {
    const masters = ['OEM Product', 'OEM Product Revision', 'OEM Option Set', 'OEM Asset', 'OEM Asset Revision', 'OEM Customer Brand', 'OEM Default Profile'];
    frappe.prompt([{fieldname: 'doctype', label: __('Catalogue record type'), fieldtype: 'Select', options: masters, reqd: 1},
        {fieldname: 'name', label: __('Existing record name (leave blank to create)'), fieldtype: 'Data'}], values => srv_erp.oem.edit_master(values.doctype, values.name || null), __('Catalogue administration'));
};
