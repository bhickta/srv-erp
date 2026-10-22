const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const native = ["Native", "blue", "status,=,To Bill"];
const context = vm.createContext({
  frappe: {
    listview_settings: { "Sales Order": { get_indicator: () => native } },
    ui: { form: { on() {} } },
  },
  __: (text) => text,
  locals: { "Workflow State": { Approved: { style: "Success" } } },
});
vm.runInContext(
  fs.readFileSync(path.join(root, "public/js/sales_order_list.js"), "utf8"),
  context,
);
vm.runInContext(
  fs.readFileSync(path.join(root, "public/js/sales_order.js"), "utf8"),
  context,
);
const indicator = context.frappe.listview_settings["Sales Order"].get_indicator;
const complete = {
  docstatus: 1,
  status: "To Bill",
  workflow_state: "Approved",
  delivery_status: "Fully Delivered",
};
assert.equal(indicator(complete)[0], "Complete (Delivered)");
assert.equal(indicator(complete)[1], "green");
assert.match(indicator(complete)[2], /delivery_status,=,Fully Delivered/);
assert.equal(indicator({ ...complete, status: "Closed" })[0], "Closed");
assert.equal(indicator({ ...complete, status: "On Hold" })[0], "On Hold");
assert.equal(
  indicator({ ...complete, docstatus: 2, status: "Cancelled" })[0],
  "Cancelled",
);
assert.equal(
  indicator({ ...complete, docstatus: 0, workflow_state: "Pending" })[0],
  "Pending",
);
assert.equal(
  indicator({ ...complete, delivery_status: "Partly Delivered" })[0],
  "Approved",
);
assert.equal(indicator({ docstatus: 1, status: "To Bill" }), native);
const calls = [];
const frm = {
  doc: { ...complete },
	toolbar: { set_indicator: () => calls.push(["regular"]) },
  page: {
    set_indicator: (...args) => calls.push(args),
    clear_indicator: () => calls.push(["clear"]),
  },
};
context.refresh_sales_order_delivery_indicator(frm);
assert.equal(calls[0][0], "Complete (Delivered)");
assert.equal(
  frm.doc.status,
  "To Bill",
  "Billing lifecycle must remain unchanged",
);
frm.doc.delivery_status = "Partly Delivered";
context.refresh_sales_order_delivery_indicator(frm);
assert.equal(calls.at(-1)[0], "regular");
frm.doc = { ...complete, status: "Closed" };
const before = calls.length;
context.refresh_sales_order_delivery_indicator(frm);
assert.equal(calls.length, before, "Do not replace Closed status");
process.stdout.write(
  "PASS: delivered form/list status, billing independence, draft/cancel/hold/closed states and delivery reversal\n",
);
