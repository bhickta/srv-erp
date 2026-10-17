// Run with node --test srv_erp/tests/js/test_oem_catalog.cjs; no bench or DOM package required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const root = path.resolve(__dirname, '../../..');
const deferred = () => {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return {promise, resolve, reject};
};

// Small rendering double: retain event callbacks and visible state, so tests
// exercise the real event handlers rather than reproducing their logic.
class Element {
    constructor(markup = '') { this.markup = markup; this.nodes = []; this.lookups = {}; this.events = {}; this.props = {}; }
    find(selector) {
        const class_name = selector.startsWith('.') ? selector.slice(1) : null;
        const match = class_name && this.nodes.find(node => node.markup.includes(class_name) && !node.removed);
        return match || (this.lookups[selector] ||= new Element(selector));
    }
    html(value) { this.markup = value; this.nodes = []; this.lookups = {}; return this; }
    text(value) { if (value === undefined) return this.content; this.content = value; return this; }
    val(value) { if (!arguments.length) return this.value; this.value = value; return this; }
    prop(key, value) { if (arguments.length === 1) return this.props[key]; this.props[key] = value; return this; }
    attr() { return this; }
    append(...nodes) { this.nodes.push(...nodes); return this; }
    appendTo(parent) { parent.append(this); return this; }
    empty() { this.nodes = []; return this; }
    remove() { this.removed = true; return this; }
    on(event, callback) { this.events[event] = callback; return this; }
    addClass() { return this; }
}

function environment() {
    let uuid = 0;
    const controls = {};
    const context = vm.createContext({
        console, setTimeout, clearTimeout, crypto: {randomUUID: () => `command-${++uuid}`},
        __: value => value, $: value => new Element(value), srv_erp: {oem: {}},
        frappe: {
            provide() {}, pages: {'oem-catalog': {}}, user_roles: [], utils: {},
            ui: {
                make_app_page: () => ({body: new Element()}),
                form: {
                    on() {}, make_control: ({df}) => {
                        const control = {df, value: '', get_value() { return this.value; },
                            set_value(value) { this.value = value; }, refresh() { this.refreshed = true; }};
                        controls[df.fieldname] = control;
                        return control;
                    },
                },
            },
            show_alert() {},
        },
    });
    const load = file => vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context, {filename: file});
    load('srv_erp/public/js/oem_catalog/api.js');
    load('srv_erp/public/js/oem_catalog/configurator.js');
    return {context, controls, oem: context.srv_erp.oem, load};
}

test('latest request guard rejects reordered completions, including repeated context', () => {
    const {oem} = environment();
    const start = oem.latest_request();
    const customer_a = start(), customer_b = start(), customer_a_again = start();
    assert.equal(customer_a(), false);
    assert.equal(customer_b(), false);
    assert.equal(customer_a_again(), true);
    assert.equal(oem.latest_request()()(), true, 'separate consumers have independent guards');
});

test('Sales Order brand scope keeps the newest response and isolates forms', async () => {
    const {context, oem, load} = environment();
    load('srv_erp/public/js/oem_catalog/sales_order.js');
    const pending = [];
    oem.customer_brands = () => { const request = deferred(); pending.push(request); return request.promise; };
    const make_form = () => ({doc: {customer: 'A', company: 'Company', brand_filter: 'B-brand'},
        set_query(field, query) { this.query = query; }, async set_value(field, value) { this.doc[field] = value; }});
    const form = make_form(), other = make_form();
    const older = context.oem_scope_brand(form);
    form.doc.customer = 'B';
    const newer = context.oem_scope_brand(form), independent = context.oem_scope_brand(other);
    pending[1].resolve([{value: 'B-brand'}]); await newer;
    pending[2].resolve([{value: 'other-brand'}]); await independent;
    pending[0].resolve([{value: 'A-brand'}]); await older;
    assert.equal(form.doc.brand_filter, 'B-brand');
    assert.deepEqual(Array.from(form.query().filters.name[1]), ['B-brand']);
    assert.deepEqual(Array.from(other.query().filters.name[1]), ['other-brand']);
});

test('catalogue page ignores stale brand options and default selection', async () => {
    const {context, controls, oem, load} = environment();
    const pending = [];
    oem.customer_brands = () => { const request = deferred(); pending.push(request); return request.promise; };
    load('srv_erp/oem_catalog/page/oem_catalog/oem_catalog.js');
    context.frappe.pages['oem-catalog'].on_page_load({});
    controls.customer.value = 'A'; controls.customer.df.onchange();
    controls.customer.value = 'B'; controls.customer.df.onchange();
    pending[1].resolve([{value: 'B-brand', default: true}]); await new Promise(setImmediate);
    pending[0].resolve([{value: 'A-brand', default: true}]); await new Promise(setImmediate);
    assert.equal(controls.brand.value, 'B-brand');
    assert.deepEqual(Array.from(controls.brand.df.get_query().filters.name[1]), ['B-brand']);
});

test('stale failed brand lookup cannot un-scope a successful newer lookup', async () => {
    const {context, oem, load} = environment();
    load('srv_erp/public/js/oem_catalog/sales_order.js');
    oem._ui_settings = {require_customer_brand: true};
    const older = deferred(), newer = deferred();
    oem.call = (method, args) => args.source_context.customer === 'A' ? older.promise : newer.promise;
    const form = {doc: {customer: 'A', company: 'Company', brand_filter: 'B-brand'},
        set_query(field, query) { this.query = query; }, async set_value(field, value) { this.doc[field] = value; }};
    const old_scope = context.oem_scope_brand(form);
    await new Promise(setImmediate);
    form.doc.customer = 'B';
    const new_scope = context.oem_scope_brand(form);
    newer.resolve({brands: [{value: 'B-brand'}]}); await new_scope;
    older.reject(new Error('offline')); await old_scope;
    assert.deepEqual(Array.from(form.query().filters.name[1]), ['B-brand']);
});

test('Configure wait follows a changed context instead of finishing with an older request', async () => {
    const {context, oem, load} = environment();
    load('srv_erp/public/js/oem_catalog/sales_order.js');
    const pending = [];
    oem.customer_brands = () => { const request = deferred(); pending.push(request); return request.promise; };
    const form = {doc: {customer: 'A', company: 'Company'}, set_query() {}};
    context.oem_scope_brand(form);
    let finished = false;
    const wait = context.oem_wait_brand_scope(form).then(() => { finished = true; });
    form.doc.customer = 'B'; context.oem_scope_brand(form);
    pending[0].resolve(null); await new Promise(setImmediate);
    assert.equal(finished, false);
    pending[1].resolve(null); await wait;
    assert.equal(finished, true);
});

function configurator(oem) {
    const instance = Object.create(oem.Configurator.prototype);
    Object.assign(instance, {root: new Element(), sequence: 0, command: null, draftCommand: null,
        product: 'Product', context: {customer: 'Customer'}, source: {adapter: 'standalone'},
        values: {colour: 'blue', empty: '', absent: undefined, unknown: 'discard', flag: false, zero: 0},
        configuration: {configuration_token: 'token', fields: [{attribute_key: 'colour'}, {attribute_key: 'empty'},
            {attribute_key: 'absent'}, {attribute_key: 'flag'}, {attribute_key: 'zero'}]},
        dialog: {hide() { this.hidden = true; }},
    });
    instance.root.find('.oem-package-choice').val('unit');
    return instance;
}

test('payload allows only schema fields and preserves false and zero', () => {
    const {oem} = environment(), instance = configurator(oem);
    const payload = JSON.parse(JSON.stringify(instance.payload()));
    assert.deepEqual(payload.values, {colour: 'blue', flag: false, zero: 0});
    assert.equal(payload.configuration_token, 'token');
    assert.equal(payload.package_choice, 'unit');
});

test('input invalidation clears preview, confirmation and command identities', () => {
    const {oem} = environment(), instance = configurator(oem);
    const panel = instance.root.find('.oem-review');
    const confirm = instance.root.find('.oem-confirm');
    instance.command = 'uncertain-submit'; instance.draftCommand = 'uncertain-draft';
    panel.text('Previous approved preview');
    instance.invalidate();
    assert.equal(instance.sequence, 1);
    assert.equal(instance.command, null);
    assert.equal(instance.draftCommand, null);
    assert.equal(confirm.removed, true);
    assert.equal(panel.content, 'Choices changed. Review again.');
});

test('rendered attribute and packaging changes both invalidate confirmation', async () => {
    const {oem} = environment(), instance = configurator(oem);
    instance.edited = new Set();
    oem.call = async () => ({display_name: 'Product', fields: [{attribute_key: 'colour', label: 'Colour', data_type: 'Text'}],
        packages: [{code: 'unit', label: 'Unit', factor: 1, uom: 'Nos', stock_uom: 'Nos'}]});
    await instance.configure('Product');
    const input = instance.root.find('.oem-attributes').nodes[0].nodes[1];
    instance.command = 'old-command';
    input.val('green'); input.events['change input']();
    assert.equal(instance.values.colour, 'green');
    assert.equal(instance.command, null);
    instance.command = 'another-command'; instance.draftCommand = 'draft-command';
    const pack = instance.root.find('.oem-package').nodes[1];
    pack.events.change();
    assert.equal(instance.command, null);
    assert.equal(instance.draftCommand, null);
    assert.equal(instance.root.find('.oem-review').content, 'Choices changed. Review again.');
});

test('stale preview cannot render after input changes', async () => {
    const {oem} = environment(), instance = configurator(oem), pending = deferred();
    oem.call = () => pending.promise;
    const review = instance.review();
    instance.invalidate();
    pending.resolve({summary: 'Stale result', values: {}, readiness: {}});
    await review;
    const panel = instance.root.find('.oem-review');
    assert.equal(panel.content, 'Choices changed. Review again.');
    assert.equal(panel.nodes.length, 0);
});

test('stale draft completion cannot replace edited state or clear its retry identity', async () => {
    const {oem} = environment(), instance = configurator(oem), pending = deferred();
    oem.call = () => pending.promise;
    const save = instance.saveDraft();
    instance.invalidate();
    instance.draftCommand = 'new-input-command';
    pending.resolve({draft: 'Old draft'}); await save;
    assert.equal(instance.draftCommand, 'new-input-command');
    assert.equal(instance.root.find('.oem-review').content, 'Choices changed. Review again.');
});

test('uncertain submission retry reuses UUID; editing requires review and a fresh UUID', async () => {
    const {oem} = environment(), instance = configurator(oem), keys = [];
    oem.call = async (method, args) => {
        if (method === 'preview_configuration') return {summary: 'Ready', values: {}, readiness: {}, item_code: 'Item'};
        keys.push(args.idempotency_key);
        if (keys.length === 1) throw new Error('connection lost');
        return {item_code: 'Item'};
    };
    await instance.review();
    const confirm = instance.root.find('.oem-review').nodes.at(-1);
    await confirm.events.click();
    assert.equal(confirm.prop('disabled'), false);
    await confirm.events.click();
    assert.equal(keys[0], keys[1]);
    instance.invalidate();
    await confirm.events.click();
    assert.equal(keys.length, 2, 'old confirmation cannot submit changed input');
    await instance.review();
    await instance.root.find('.oem-review').nodes.at(-1).events.click();
    assert.notEqual(keys[2], keys[0]);
});
