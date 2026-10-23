const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function setup() {
  const handlers = {};
  const row = {
    doctype: "SRV Production Schedule Item",
    name: "ROW-1",
    idx: 1,
  };
  const items = {
    T1: {
      item_name: "Template One",
      stock_uom: "Nos",
      custom_production_supervisor: "one",
    },
    T2: {
      item_name: "Template Two",
      stock_uom: "Kg",
      custom_production_supervisor: "two",
    },
    V1: { variant_of: "T1", item_name: "Variant One" },
    V2: { variant_of: "T2", item_name: "Variant Two" },
    V3: { variant_of: "T1", item_name: "Variant Three" },
  };
  const frm = { doc: { items: [row], docstatus: 0 } };
  const frappe = {
    ui: {
      form: {
        on: (doctype, events) => {
          handlers[doctype] = events;
        },
      },
    },
    db: {
      get_value: async (doctype, code) => ({ message: items[code] || {} }),
    },
    model: {
      async set_value(doctype, name, field, value) {
        const values = typeof field === "object" ? field : { [field]: value };
        const changed = Object.entries(values).filter(
          ([key, next]) => row[key] !== next,
        );
        // Frappe assigns the whole batch before running field triggers serially.
        for (const [key, next] of changed) row[key] = next;
        for (const [key] of changed)
          await handlers[doctype]?.[key]?.(frm, doctype, name);
      },
    },
  };
  const context = vm.createContext({
    frappe,
    locals: { [row.doctype]: { [row.name]: row } },
    __: (s) => s,
  });
  vm.runInContext(
    fs.readFileSync(
      path.resolve(
        __dirname,
        "../../srv_erp/doctype/srv_production_schedule/srv_production_schedule.js",
      ),
      "utf8",
    ),
    context,
  );
  const set = (values) => frappe.model.set_value(row.doctype, row.name, values);
  return { row, frappe, set, items };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("batch-filled template and matching variant retain the selected code and name", async () => {
  const { row, set } = setup();
  await set({ template: "T1", item_code: "V1" });
  assert.equal(row.item_code, "V1");
  assert.equal(row.item_name, "Variant One");
  assert.equal(row.uom, "Nos");
  assert.equal(row.supervisor, "one");
});

test("changing the template clears an incompatible variant", async () => {
  const { row, set } = setup();
  await set({ template: "T1", item_code: "V1" });
  await set({ template: "T2" });
  assert.equal(row.item_code, null);
  assert.equal(row.item_name, "Template Two");
  assert.equal(row.uom, "Kg");
});

test("slow template lookup cannot overwrite a later template and variant", async () => {
  const { row, set, frappe, items } = setup();
  const slow = deferred();
  frappe.db.get_value = async (_doctype, code) =>
    code === "T1" ? slow.promise : { message: items[code] };
  const first = set({ template: "T1" });
  await set({ template: "T2", item_code: "V2" });
  slow.resolve({ message: items.T1 });
  await first;
  assert.equal(row.template, "T2");
  assert.equal(row.item_code, "V2");
  assert.equal(row.item_name, "Variant Two");
  assert.equal(row.uom, "Kg");
});

test("slow variant lookup cannot overwrite the latest selected item name", async () => {
  const { row, set, frappe, items } = setup();
  await set({ template: "T1" });
  const slow = deferred();
  frappe.db.get_value = async (_doctype, code) =>
    code === "V1" ? slow.promise : { message: items[code] };
  const first = set({ item_code: "V1" });
  await set({ item_code: "V3" });
  slow.resolve({ message: items.V1 });
  await first;
  assert.equal(row.item_code, "V3");
  assert.equal(row.item_name, "Variant Three");
});

test("clearing the template clears the old item and defaults", async () => {
  const { row, set } = setup();
  await set({ template: "T1", item_code: "V1" });
  await set({ template: null });
  assert.equal(row.item_code, null);
  assert.equal(row.item_name, "");
  assert.equal(row.uom, null);
  assert.equal(row.supervisor, null);
});

test("entry validation identifies each missing variant row, template and date", () => {
  const handlers = {};
  const context = vm.createContext({
    frappe: {
      ui: {
        form: {
          on: (doctype, events) => {
            handlers[doctype] = events;
          },
        },
      },
      utils: {
        escape_html: (value) =>
          value.replaceAll("<", "&lt;").replaceAll(">", "&gt;"),
      },
      throw: (message) => {
        throw new Error(message);
      },
    },
    __: (text, values = []) =>
      text.replace(/\{(\d+)\}/g, (_, index) => values[index]),
  });
  vm.runInContext(
    fs.readFileSync(
      path.resolve(
        __dirname,
        "../../srv_erp/doctype/srv_production_entry/srv_production_entry.js",
      ),
      "utf8",
    ),
    context,
  );
  const validate = handlers["SRV Production Entry"].validate;
  assert.throws(
    () =>
      validate({
        doc: {
          items: [
            { idx: 1, template: "CB 314", planned_date: "2026-10-21" },
            { idx: 2, template: "CB 300", planned_date: "2026-10-21" },
          ],
        },
      }),
    /Row 1: template CB 314, schedule date 2026-10-21.*Row 2: template CB 300/,
  );
  assert.doesNotThrow(() =>
    validate({ doc: { items: [{ idx: 1, item_code: "V1" }] } }),
  );
});
