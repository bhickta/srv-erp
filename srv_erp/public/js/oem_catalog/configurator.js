frappe.provide('srv_erp.oem');
class OEMConfigurator {
    constructor(context, source, on_result) {
        this.context = {...context}; this.source = source; this.on_result = on_result;
        this.values = {}; this.edited = new Set(); this.sequence = 0; this.command = null;
        this.dialog = new frappe.ui.Dialog({title: __('Configure OEM Product'), size: 'extra-large', fields: [
            {fieldname: 'body', fieldtype: 'HTML'},
        ]});
        this.dialog.$wrapper.addClass('oem-config-dialog');
        this.root = this.dialog.fields_dict.body.$wrapper;
        this.dialog.show(); this.catalogue();
    }
    status(message) {
        this.root.find('[role="status"]').text(message);
    }
    async catalogue() {
        this.root.html(`<div class="oem-stack"><label>${__('Search products')}<input type="search" class="form-control oem-search"></label><div role="status" aria-live="polite"></div><div class="oem-products"></div></div>`);
        const search = async () => {
            const sequence = ++this.sequence;
            this.status(__('Loading products…'));
            try {
                const result = await srv_erp.oem.call('search_products', {context: this.context, query: this.root.find('.oem-search').val()});
                if (sequence !== this.sequence) return;
                const container = this.root.find('.oem-products').empty();
                result.products.forEach(product => {
                    const button = $('<button type="button" class="oem-product btn btn-default"></button>');
                    button.append($('<strong>').text(product.display_name), $('<small>').text(`${product.catalogue_code} · ${product.item_group}`));
                    // File previews are served by the ordinary authenticated File route.
                    if (product.image && product.image.startsWith('/private/files/')) button.prepend($('<img loading="lazy">').attr({src: product.image, alt: product.display_name}));
                    button.on('click', () => this.configure(product.name)); container.append(button);
                });
                this.status(result.products.length ? __('Choose a product.') : __('No permitted products found.'));
            } catch (error) { if (sequence === this.sequence) this.status(__('Unable to load products. Check your connection and permissions.')); }
        };
        let timer;
        this.root.find('.oem-search').on('input', () => { clearTimeout(timer); ++this.sequence; timer = setTimeout(search, 200); });
        await search();
    }
    async configure(product) {
        const sequence = ++this.sequence;
        this.product = product; this.command = null; this.draftCommand = null;
        this.status(__('Loading configuration…'));
        try {
            const configuration = await srv_erp.oem.call('get_configuration', {product, context: this.context});
            if (sequence !== this.sequence) return;
            this.configuration = configuration;
            this.root.html('<div class="oem-stack"><div class="oem-heading"></div><div class="oem-attributes"></div><div class="oem-package"></div><div class="oem-review" role="status" aria-live="polite"></div><div class="oem-actions"></div></div>');
            this.root.find('.oem-heading').append($('<h4>').text(configuration.display_name), $('<button class="btn btn-default" type="button">').text(__('Change product')).on('click', () => this.catalogue()));
            const attributes = this.root.find('.oem-attributes');
            configuration.fields.forEach(field => {
                const key = field.attribute_key, previous = this.values[key];
                const wrapper = $('<div class="oem-field">'), label = $('<label>').text(__(field.label) + (field.required ? ' *' : ''));
                const id = `oem-${srv_erp.oem.uuid()}`; let input;
                if (field.data_type === 'Boolean') input = $('<input type="checkbox">');
                else if (field.data_type === 'Decimal') input = $('<input type="number" class="form-control">').attr({min: field.min_value || undefined, max: field.max_value || undefined, step: field.increment || 'any'});
                else if (field.data_type === 'Text') input = $('<textarea class="form-control" rows="2">');
                else {
                    input = $('<select class="form-control">').attr('multiple', field.multi_select ? 'multiple' : null);
                    if (!field.multi_select) input.append($('<option>').val('').text(__('Choose…')));
                    field.options.forEach(option => input.append($('<option>').val(option.value).text(option.label)));
                }
                input.attr({id, 'aria-required': field.required ? 'true' : 'false'}); label.attr('for', id);
                let value = this.edited.has(key) ? previous : field.default?.value;
                if (value === undefined && field.options?.length === 1) value = field.options[0].value;
                if (field.data_type === 'Boolean') { input.prop('checked', Boolean(value)); value = Boolean(value); }
                else input.val(value ?? '');
                this.values[key] = value ?? '';
                if (field.default?.locked) input.prop('disabled', true);
                const note = $('<small>').text(field.default ? `${__('From')} ${field.default.source_type} · ${field.default.locked ? __('Locked') : field.default.explanation || ''}` : __('Choose an approved value.'));
                input.on('change input', () => {
                    this.values[key] = field.data_type === 'Boolean' ? input.prop('checked') : input.val();
                    this.edited.add(key); this.command = null; this.draftCommand = null; this.draftCommand = null; ++this.sequence;
                    this.root.find('.oem-review').text(__('Choices changed. Review again.'));
                });
                wrapper.append(label, input, note); attributes.append(wrapper);
            });
            const pack = $('<select class="form-control oem-package-choice">').attr('aria-label', __('Packaging'));
            configuration.packages.forEach(p => pack.append($('<option>').val(p.code).text(`${p.label}: 1 ${p.uom} = ${p.factor} ${p.stock_uom}`)));
            pack.on('change', () => { this.command = null; this.draftCommand = null; ++this.sequence; });
            this.root.find('.oem-package').append($('<label>').text(__('Packaging')), pack);
            const actions = this.root.find('.oem-actions');
            $('<button type="button" class="btn btn-primary">').text(__('Review')).on('click', () => this.review()).appendTo(actions);
            $('<button type="button" class="btn btn-default">').text(__('Save configuration draft')).on('click', () => this.saveDraft()).appendTo(actions);
        } catch (error) { if (sequence === this.sequence) this.status(__('Configuration could not load. Refresh and check context.')); }
    }
    payload() {
        const keys = new Set(this.configuration.fields.map(f => f.attribute_key));
        return {api_version: 1, product: this.product, configuration_token: this.configuration.configuration_token,
            values: Object.fromEntries(Object.entries(this.values).filter(([key, value]) => keys.has(key) && value !== '' && value !== undefined)),
            package_choice: this.root.find('.oem-package-choice').val(), context: this.context, source: this.source};
    }
    async review() {
        const sequence = ++this.sequence, payload = this.payload();
        const panel = this.root.find('.oem-review').text(__('Validating…'));
        this.root.find('.oem-confirm').remove();
        try {
            const preview = await srv_erp.oem.call('preview_configuration', {payload});
            if (sequence !== this.sequence) return;
            panel.empty().append($('<h5>').text(preview.summary));
            Object.entries(preview.values).forEach(([key, value]) => panel.append($('<p>').text(`${key}: ${Array.isArray(value) ? value.join(', ') : value}`)));
            panel.append($('<p>').text(preview.item_code ? `${__('Existing stock Item')}: ${preview.item_code}` : __('Approval is required. No Item will be created by this request.')));
            if (preview.readiness.missing?.length) panel.append($('<p>').text(preview.readiness.missing.join(', ')));
            const confirm = $('<button type="button" class="btn btn-primary oem-confirm">').text(preview.item_code ? __('Use existing Item') : __('Request approval'));
            confirm.on('click', async () => {
                if (sequence !== this.sequence || confirm.prop('disabled')) return;
                confirm.prop('disabled', true); this.command ||= srv_erp.oem.uuid();
                try {
                    const result = await srv_erp.oem.call('submit_configuration', {payload, idempotency_key: this.command});
                    if (sequence !== this.sequence) return;
                    await this.on_result?.(result, payload, preview);
                    this.dialog.hide();
                } catch (error) { panel.append($('<p>').text(__('No confirmed result. Retry with the same choices; the command is safe to replay.'))); confirm.prop('disabled', false); }
            });
            panel.append(confirm);
        } catch (error) { if (sequence === this.sequence) panel.text(__('Review failed. Check required choices and refresh stale configuration.')); }
    }
    async saveDraft() {
        const button = this.root.find('.oem-actions button').prop('disabled', true);
        this.draftCommand ||= srv_erp.oem.uuid();
        try {
            const result = await srv_erp.oem.call('save_draft', {payload: this.payload(), idempotency_key: this.draftCommand});
            this.root.find('.oem-review').text(`${__('Draft saved')}: ${result.draft}`); this.draftCommand = null;
        } finally { button.prop('disabled', false); }
    }
}
srv_erp.oem.Configurator = OEMConfigurator;
