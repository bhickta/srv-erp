const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(items = [], doctype = 'Delivery Note', references = []) {
	const doc = { doctype, customer: 'C', company: 'CO', items, package_barcodes: [] };
	const frm = { doctype, doc, fields_dict: { scan_barcode: { value: '', set_value(value) { this.value = value; } },
		items: { grid: { doctype: 'Delivery Note Item' } } }, dirty() {}, cscript: {} };
	let prompts = 0;
	let delegated = 0;
	const package_barcode = {
		get_item_uom_details: async () => ({ stock_uom: 'PCS', conversion_factors: { BOX: 20, PCS: 1 } }),
		refresh_barcode_only_items() {}, render_scan_review() {}, record_successful_scan() {}, record_blocked_scan() {},
	};
	class BaseScanner {
		constructor(opts) { Object.assign(this, { frm: opts.frm, items_table_name: 'items',
			scan_barcode_field: opts.frm.fields_dict.scan_barcode }); }
		update_table() { delegated++; return Promise.resolve('base'); }
		get_row_to_modify_on_scan() { delegated++; return 'base'; }
		set_selector_trigger_flag() {}
		revert_selector_flag() {}
		is_duplicate_serial_no(row, serial) { return serial && (row.serial_no || '').includes(serial); }
		async set_serial_no() {}
		async set_batch_no() {}
		async set_barcode() {}
		show_scan_message() {}
		clean_up() {}
		play_success_sound() {}
		play_fail_sound() {}
		show_alert() {}
	}
	const frappe = { flags: {}, meta: { has_field: () => true },
		call: async () => ({ message: references }),
		model: {
			add_child(doc, doctype, field) {
				const row = { name: `r${doc[field].length + 1}`, doctype, idx: doc[field].length + 1 };
				doc[field].push(row); return row;
			},
			async set_value(doctype, name, field, value) {
				const row = doc.items.find(row => row.name === name);
				Object.assign(row, typeof field === 'string' ? { [field]: value } : field);
				row.stock_qty = Number(row.qty || 0) * Number(row.conversion_factor || 0);
			},
		},
		throw(message) { throw new Error(message); },
		ui: { Dialog: class {
			constructor(opts) { Object.assign(this, opts); }
			show() { prompts++; this.primary_action({ target: this.fields[0].options[0] }); }
			hide() { this.onhide?.(); }
		} },
	};
	const ctx = vm.createContext({ srv_erp: { package_barcode }, frappe,
		erpnext: { utils: { BarcodeScanner: BaseScanner } }, flt: value => Number(value || 0),
		__: (text, args = []) => text.replace(/\{(\d+)\}/g, (_, n) => args[n]), refresh_field() {}, console,
	});
	vm.runInContext(fs.readFileSync(path.join(__dirname, '../../public/js/package_barcode/stock_scanner.js'), 'utf8'), ctx);
	const scanner = new package_barcode.PackageBarcodeScanner({ frm });
	return { scanner, frm, ctx, prompts: () => prompts, delegated: () => delegated };
}

const row = (uom = 'BOX', extra = {}) => ({ name: 'r1', idx: 1, doctype: 'Delivery Note Item',
	item_code: 'I', uom, qty: 0, conversion_factor: uom === 'BOX' ? 20 : 1,
	against_sales_order: 'SO', so_detail: 'SOI', rate: 123, warehouse: 'W', ...extra });
const scan = uom => ({ item_code: 'I', uom, qty: 1 });

test('BOX and PCS scans create separate whole-quantity rows', async () => {
	const { scanner, frm } = setup([row()]);
	await scanner.update_table(scan('BOX'));
	await scanner.update_table(scan('PCS'));
	assert.equal(frm.doc.items.length, 2);
	assert.equal(frm.doc.items[0].qty, 1);
	assert.equal(frm.doc.items[0].stock_qty, 20);
	assert.equal(frm.doc.items[1].qty, 1);
	assert.equal(frm.doc.items[1].uom, 'PCS');
	assert.equal(frm.doc.items[1].stock_qty, 1);
	assert.equal(frm.doc.items[1].so_detail, 'SOI');
	assert.equal(frm.doc.items[0].uom, 'BOX');
	assert.equal(frm.doc.items[0].rate, 123);
	assert.equal(frm.doc.items[0].so_detail, 'SOI');
});
test('PCS first then BOX creates one row per UOM', async () => {
	const { scanner, frm } = setup([row('PCS')]);
	await scanner.update_table(scan('PCS'));
	await scanner.update_table(scan('BOX'));
	assert.equal(frm.doc.items.length, 2);
	assert.equal(frm.doc.items[0].qty, 1);
	assert.equal(frm.doc.items[0].uom, 'PCS');
	assert.equal(frm.doc.items[1].qty, 1);
	assert.equal(frm.doc.items[1].uom, 'BOX');
});
test('new scanned row receives the Sales Order line and barcode UOM', async () => {
	const { scanner, frm } = setup([], 'Delivery Note', [{ against_sales_order: 'SO', so_detail: 'SOI', warehouse: 'W' }]);
	await scanner.update_table(scan('PCS'));
	assert.equal(frm.doc.items[0].so_detail, 'SOI');
	assert.equal(frm.doc.items[0].against_sales_order, 'SO');
	assert.equal(frm.doc.items[0].uom, 'PCS');
	assert.equal(frm.doc.items[0].qty, 1);
});
test('existing unlinked row is resolved before quantity is added', async () => {
	const { scanner, frm } = setup([row('PCS', { against_sales_order: '', so_detail: '' })], 'Delivery Note',
		[{ against_sales_order: 'SO', so_detail: 'SOI' }]);
	await scanner.update_table(scan('PCS'));
	assert.equal(frm.doc.items[0].so_detail, 'SOI');
	assert.equal(frm.doc.items[0].qty, 1);
});
test('different Sales Order lines require selection even when UOM is equal', async () => {
	const state = setup([row(), row('BOX', { name: 'r2', idx: 2, so_detail: 'SOI2' })]);
	await state.scanner.update_table(scan('BOX'));
	assert.equal(state.prompts(), 1);
	assert.equal(state.frm.doc.items[1].qty, 0);
});
test('different UOM creates a new row and keeps the existing SO line', async () => {
	const state = setup([row('PCS'), row('PCS', { name: 'r2', idx: 2 })]);
	await state.scanner.update_table(scan('BOX'));
	assert.equal(state.prompts(), 0);
	assert.equal(state.frm.doc.items.length, 3);
	assert.equal(state.frm.doc.items[2].uom, 'BOX');
});
test('unknown UOM blocks before a row or quantity is changed', async () => {
	const { scanner, frm } = setup([row()]);
	await assert.rejects(scanner.update_table(scan('Kg')), /not configured/);
	assert.equal(frm.doc.items[0].qty, 0);
	assert.equal(frm.doc.items.length, 1);
});
test('warehouse mismatch creates a referenced row rather than changing warehouse', async () => {
	const state = setup([row()], 'Delivery Note', [{ against_sales_order: 'SO', so_detail: 'SOI' }]);
	await state.scanner.update_table({ ...scan('BOX'), default_warehouse: 'Other' });
	assert.equal(state.frm.doc.items.length, 2);
	assert.equal(state.frm.doc.items[0].warehouse, 'W');
	assert.equal(state.frm.doc.items[1].so_detail, 'SOI');
});
test('duplicate package policy remains independent of UOM', () => {
	const { scanner, frm } = setup();
	frm.doc.package_barcodes.push({ package_barcode: 'P', uom: 'BOX' });
	assert.equal(scanner.is_duplicate_package_barcode('P'), true);
});
for (const doctype of ['Stock Entry', 'Stock Reconciliation']) {
	test(`${doctype} update_table still delegates to ERPNext`, async () => {
		const state = setup([], doctype);
		assert.equal(await state.scanner.update_table(scan('BOX')), 'base');
		assert.equal(state.delegated(), 1);
	});
}
test('Stock Reconciliation retains its package UOM row selection', () => {
	const state = setup([row('PCS')], 'Stock Reconciliation');
	state.scanner.stock_reconciliation_package_uom = 'BOX';
	assert.equal(state.scanner.get_row_to_modify_on_scan('I', null, null, null, 'W').name, 'r1');
});
test('returns retain the base scan path', async () => {
	const state = setup(); state.frm.doc.is_return = 1;
	assert.equal(await state.scanner.update_table(scan('BOX')), 'base');
});

function load(state, filename) {
	vm.runInContext(fs.readFileSync(path.join(__dirname, '../../public/js', filename), 'utf8'), state.ctx);
}
test('Force Barcode Only does not reset an in-progress separate-UOM scan', async () => {
	const state = setup([row()]);
	load(state, 'package_barcode/quantity_control.js');
	state.frm.package_barcode_only_items = new Set(['I']);
	const original = state.ctx.frappe.model.set_value;
	state.ctx.frappe.model.set_value = async (...args) => {
		await original(...args);
		if (args[2] === 'qty') await state.ctx.srv_erp.package_barcode.enforce_barcode_only_qty(state.frm, true);
	};
	await state.scanner.update_table(scan('PCS'));
	assert.equal(state.frm.doc.items[0].qty, 0);
	assert.equal(state.frm.doc.items[1].qty, 1);
	assert.equal(state.frm.doc.items[1].uom, 'PCS');
	assert.equal(state.frm.package_barcode_delivery_scanning, false);
});
test('Force Barcode Only enforces each item/UOM count separately', async () => {
	const state = setup([row(), row('PCS', { name: 'r2', idx: 2 })]);
	load(state, 'package_barcode/quantity_control.js');
	state.frm.package_barcode_only_items = new Set(['I']);
	state.frm.doc.package_barcodes = [{ item_code: 'I', uom: 'BOX' }, { item_code: 'I', uom: 'PCS' }];
	await state.ctx.srv_erp.package_barcode.enforce_barcode_only_qty(state.frm, true);
	assert.equal(state.frm.doc.items[0].qty, 1);
	assert.equal(state.frm.doc.items[1].qty, 1);
});
test('Force Barcode Only never assigns the whole item total to each SO row', async () => {
	const state = setup([row('BOX', { qty: 1 }), row('PCS', { name: 'r2', idx: 2, qty: 1 })]);
	load(state, 'package_barcode/quantity_control.js');
	state.frm.package_barcode_only_items = new Set(['I']);
	state.frm.doc.package_barcodes = [{ item_code: 'I', uom: 'BOX' }, { item_code: 'I', uom: 'PCS' }];
	await state.ctx.srv_erp.package_barcode.enforce_barcode_only_qty(state.frm, true);
	assert.equal(state.frm.doc.items[0].qty, 1);
	assert.equal(state.frm.doc.items[1].qty, 1);
});
test('scan review reports package UOM and converted stock quantity', async () => {
	const state = setup([row()]);
	let html;
	state.ctx.frappe.dom = { set_style() {} };
	state.ctx.frappe.utils = { escape_html: String };
	state.frm.fields_dict.scan_barcode.$wrapper = { next() { return { remove() {} }; }, after(value) { html = value; } };
	load(state, 'package_barcode/scan_review.js');
	state.frm.doc.package_barcodes = [{ item_code: 'I', uom: 'BOX', barcode: 'B1' }, { item_code: 'I', uom: 'PCS', barcode: 'P1' }];
	await state.ctx.srv_erp.package_barcode.render_scan_review(state.frm);
	assert.match(html, /21 PCS/);
	assert.match(html, /P1 PCS/);
});
test('rapid duplicate package scans are serialized and the second is rejected', async () => {
	const state = setup([row()]);
	state.ctx.srv_erp.package_barcode.apply_stock_reconciliation_package_uom = () => {};
	state.ctx.frappe.call = async () => ({ message: { ...scan('PCS'), package_barcode: 'P', barcode: 'P' } });
	state.frm.fields_dict.scan_barcode.value = 'P';
	const first = state.scanner.process_scan();
	state.frm.fields_dict.scan_barcode.value = 'P';
	const second = state.scanner.process_scan();
	const results = await Promise.allSettled([first, second]);
	assert.equal(results[0].status, 'fulfilled');
	assert.equal(results[1].status, 'rejected');
	assert.equal(state.frm.doc.package_barcodes.length, 1);
	assert.equal(state.frm.doc.items[0].qty, 0);
	assert.equal(state.frm.doc.items[1].qty, 1);
});


test('repeated scans of the same UOM increment its row by whole units', async () => {
	const state = setup([row()]);
	await state.scanner.update_table(scan('BOX'));
	await state.scanner.update_table(scan('BOX'));
	assert.equal(state.frm.doc.items.length, 1);
	assert.equal(state.frm.doc.items[0].qty, 2);
});
test('fractional scan quantity is rejected before any row mutation', async () => {
	const state = setup([row()]);
	await assert.rejects(state.scanner.update_table({ ...scan('BOX'), qty: 0.5 }), /whole number/);
	assert.equal(state.frm.doc.items[0].qty, 0);
	assert.equal(state.frm.doc.items.length, 1);
});
test('a sibling variant requires explicit SO-line selection even with one match', async () => {
	const state = setup([row()], 'Delivery Note', [{ item_code: 'I', against_sales_order: 'SO', so_detail: 'SOI', is_substitution: true }]);
	await state.scanner.update_table({ ...scan('PCS'), item_code: 'SIBLING' });
	assert.equal(state.prompts(), 1);
	assert.equal(state.frm.doc.items[1].item_code, 'SIBLING');
	assert.equal(state.frm.doc.items[1].so_detail, 'SOI');
	assert.equal(state.frm.doc.items[1].qty, 1);
	assert.equal(state.frm.doc.items[0].item_code, 'I');
});
test('subsequent UOM scans retain the already chosen sibling substitution link', async () => {
	const state = setup([row('PCS', { item_code: 'SIBLING', qty: 1 })]);
	await state.scanner.update_table({ ...scan('BOX'), item_code: 'SIBLING' });
	assert.equal(state.prompts(), 0);
	assert.equal(state.frm.doc.items[1].item_code, 'SIBLING');
	assert.equal(state.frm.doc.items[1].so_detail, 'SOI');
	assert.equal(state.frm.doc.items[1].uom, 'BOX');
	assert.equal(state.frm.doc.items[1].qty, 1);
});
test('cancelling a substitution prompt creates no row and consumes no quantity', async () => {
	const state = setup([row()], 'Delivery Note', [{ item_code: 'I', against_sales_order: 'SO', so_detail: 'SOI', is_substitution: true }]);
	state.ctx.frappe.ui.Dialog = class { show() { this.onhide(); } };
	await assert.rejects(state.scanner.update_table({ ...scan('PCS'), item_code: 'SIBLING' }), /cancelled/);
	assert.equal(state.frm.doc.items.length, 1);
	assert.equal(state.frm.doc.items[0].qty, 0);
});
test('row selection never returns a convertible row with a different UOM', () => {
	const state = setup([row()]);
	assert.equal(state.scanner.get_row_to_modify_on_scan('I', null, 'PCS', null, 'W'), undefined);
});


test('an exact-variant order does not hide other sibling orders from first-scan selection', async () => {
	const state = setup([], 'Delivery Note', [
		{ item_code: 'I', against_sales_order: 'SO', so_detail: 'EXACT', is_substitution: false },
		{ item_code: 'SIBLING', against_sales_order: 'SO2', so_detail: 'SUBSTITUTE', is_substitution: true },
	]);
	let count;
	state.ctx.frappe.ui.Dialog = class {
		constructor(opts) { Object.assign(this, opts); }
		show() { count = this.fields[0].options.length; this.primary_action({ target: this.fields[0].options[1] }); }
		hide() { this.onhide?.(); }
	};
	await state.scanner.update_table(scan('PCS'));
	assert.equal(count, 2);
	assert.equal(state.frm.doc.items[0].so_detail, 'SUBSTITUTE');
	assert.equal(state.frm.doc.items[0].item_code, 'I');
});

test('Delivery Note displays whole quantities and restores original precision for returns', () => {
	const state = setup([row()]);
	let events;
	const fields = [{ fieldname: 'qty', precision: 3 }, { fieldname: 'stock_qty' }, { fieldname: 'stock_uom' }];
	state.frm.fields_dict.items.grid = {
		docfields: fields,
		update_docfield_property(name, property, value) { fields.find(field => field.fieldname === name)[property] = value; },
	};
	state.ctx.frappe.ui.form = { on(doctype, handlers) { events = handlers; } };
	state.ctx.frappe.utils = { escape_html: String };
	state.ctx.frappe.format = value => String(value);
	load(state, 'delivery_note.js');
	events.refresh(state.frm);
	assert.equal(fields[0].precision, 0);
	assert.match(fields[0].formatter(2.0, fields[0], {}, row('BOX', { stock_qty: 40, stock_uom: 'PCS' })), /^2<div/);
	state.frm.doc.is_return = 1;
	events.refresh(state.frm);
	assert.equal(fields[0].precision, 3);
});
