from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, nowtime


DEFAULT_PREVIEW_LIMIT = 500
MAX_ZEROING_ROWS = 5000


@frappe.whitelist()
def get_zero_stock_defaults() -> dict:
	return {
		"company": frappe.defaults.get_user_default("Company")
		or frappe.defaults.get_global_default("company")
		or frappe.db.get_value("Company", {}, "name"),
		"posting_date": nowdate(),
		"posting_time": nowtime(),
		"max_rows": DEFAULT_PREVIEW_LIMIT,
	}


@frappe.whitelist()
def preview_zero_stock_reconciliation(filters=None) -> dict:
	filters = parse_filters(filters)
	limit = clamp_row_limit(filters.get("max_rows"), DEFAULT_PREVIEW_LIMIT)
	rows = get_stock_rows_to_zero(filters, limit + 1)
	truncated = len(rows) > limit
	rows = rows[:limit]

	return {
		"rows": rows,
		"truncated": truncated,
		"summary": get_summary(rows, truncated),
	}


@frappe.whitelist()
def create_zero_stock_reconciliation(filters=None) -> dict:
	filters = parse_filters(filters)
	frappe.has_permission("Stock Reconciliation", "create", throw=True)

	limit = clamp_row_limit(filters.get("max_rows"), MAX_ZEROING_ROWS)
	rows = get_stock_rows_to_zero(filters, limit + 1)
	if len(rows) > limit:
		frappe.throw(
			_("Please narrow the filters. This action can create up to {0} rows at a time.").format(limit)
		)
	if not rows:
		frappe.throw(_("No non-zero stock found for the selected filters."))

	doc = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"purpose": "Stock Reconciliation",
			"company": filters.company,
			"posting_date": filters.posting_date,
			"posting_time": filters.posting_time,
			"set_posting_time": 1,
			"items": [make_zero_stock_row(row) for row in rows],
		}
	)
	doc.insert()

	return {
		"name": doc.name,
		"row_count": len(rows),
		"total_abs_qty": sum(abs(flt(row.qty)) for row in rows),
	}


def get_stock_rows_to_zero(filters: frappe._dict, limit: int) -> list[frappe._dict]:
	validate_filters(filters)
	ledger_conditions = [
		"sle.is_cancelled = 0",
		"sle.company = %(company)s",
		"wh.company = %(company)s",
		"wh.is_group = 0",
		"item.disabled = 0",
		"item.is_stock_item = 1",
		"item.has_variants = 0",
		"sle.posting_datetime <= %(posting_datetime)s",
	]
	result_conditions = ["ranked.row_rank = 1"]
	params = {
		"company": filters.company,
		"posting_datetime": f"{filters.posting_date} {filters.posting_time}",
		"limit": cint(limit),
	}

	if filters.get("warehouse"):
		warehouse = frappe.db.get_value(
			"Warehouse", filters.warehouse, ["lft", "rgt", "company"], as_dict=True
		)
		if not warehouse:
			frappe.throw(_("Warehouse {0} does not exist.").format(frappe.bold(filters.warehouse)))
		if warehouse.company != filters.company:
			frappe.throw(_("Warehouse {0} does not belong to company {1}.").format(filters.warehouse, filters.company))
		ledger_conditions.append("wh.lft >= %(warehouse_lft)s")
		ledger_conditions.append("wh.rgt <= %(warehouse_rgt)s")
		params["warehouse_lft"] = warehouse.lft
		params["warehouse_rgt"] = warehouse.rgt

	if filters.get("item_group"):
		item_group = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"], as_dict=True)
		if not item_group:
			frappe.throw(_("Item Group {0} does not exist.").format(frappe.bold(filters.item_group)))
		ledger_conditions.append("ig.lft >= %(item_group_lft)s")
		ledger_conditions.append("ig.rgt <= %(item_group_rgt)s")
		params["item_group_lft"] = item_group.lft
		params["item_group_rgt"] = item_group.rgt

	if filters.get("item_code"):
		ledger_conditions.append("sle.item_code = %(item_code)s")
		params["item_code"] = filters.item_code

	if not cint(filters.get("include_negative_stock", 1)):
		result_conditions.append("ranked.qty > 0")
	else:
		result_conditions.append("ranked.qty != 0")

	if not cint(filters.get("include_serial_batch_items", 1)):
		result_conditions.append("item.has_serial_no = 0")
		result_conditions.append("item.has_batch_no = 0")

	ledger_where_clause = " and ".join(ledger_conditions)
	result_where_clause = " and ".join(result_conditions)

	return frappe.db.sql(
		f"""
		with ranked as (
			select
				sle.item_code,
				sle.warehouse,
				sle.qty_after_transaction as qty,
				sle.valuation_rate,
				sle.posting_datetime,
				row_number() over (
					partition by sle.item_code, sle.warehouse
					order by sle.posting_datetime desc, sle.creation desc, sle.name desc
				) as row_rank
			from `tabStock Ledger Entry` sle
			inner join `tabWarehouse` wh on wh.name = sle.warehouse
			inner join `tabItem` item on item.name = sle.item_code
			inner join `tabItem Group` ig on ig.name = item.item_group
			where {ledger_where_clause}
		)
		select
			ranked.item_code,
			item.item_name,
			item.item_group,
			item.stock_uom,
			item.has_serial_no,
			item.has_batch_no,
			ranked.warehouse,
			ranked.qty,
			ranked.valuation_rate,
			ranked.posting_datetime
		from ranked
		inner join `tabItem` item on item.name = ranked.item_code
		where {result_where_clause}
		order by ranked.warehouse, ranked.item_code
		limit %(limit)s
		""",
		params,
		as_dict=True,
	)


def make_zero_stock_row(row: frappe._dict) -> dict:
	has_serial_batch = cint(row.has_serial_no) or cint(row.has_batch_no)
	valuation_rate = flt(row.valuation_rate)
	return {
		"item_code": row.item_code,
		"item_name": row.item_name,
		"item_group": row.item_group,
		"warehouse": row.warehouse,
		"qty": 0,
		"stock_uom": row.stock_uom,
		"valuation_rate": valuation_rate,
		"current_qty": flt(row.qty),
		"current_valuation_rate": valuation_rate,
		"allow_zero_valuation_rate": 1 if valuation_rate == 0 else 0,
		"reconcile_all_serial_batch": 1 if has_serial_batch else 0,
	}


def get_summary(rows: list[frappe._dict], truncated: bool) -> dict:
	return {
		"row_count": len(rows),
		"total_abs_qty": sum(abs(flt(row.qty)) for row in rows),
		"positive_rows": len([row for row in rows if flt(row.qty) > 0]),
		"negative_rows": len([row for row in rows if flt(row.qty) < 0]),
		"serial_batch_rows": len([row for row in rows if cint(row.has_serial_no) or cint(row.has_batch_no)]),
		"truncated": truncated,
	}


def parse_filters(filters) -> frappe._dict:
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		filters.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	if not filters.get("posting_date"):
		filters.posting_date = nowdate()
	if not filters.get("posting_time"):
		filters.posting_time = nowtime()
	if filters.get("include_negative_stock") is None:
		filters.include_negative_stock = 1
	if filters.get("include_serial_batch_items") is None:
		filters.include_serial_batch_items = 1
	return filters


def validate_filters(filters: frappe._dict) -> None:
	if not filters.get("company"):
		frappe.throw(_("Company is required."))
	if not frappe.db.exists("Company", filters.company):
		frappe.throw(_("Company {0} does not exist.").format(frappe.bold(filters.company)))
	if not filters.get("posting_date"):
		frappe.throw(_("Posting Date is required."))
	if not filters.get("posting_time"):
		frappe.throw(_("Posting Time is required."))


def clamp_row_limit(value, default: int) -> int:
	value = cint(value) or default
	if value < 1:
		return default
	return min(value, MAX_ZEROING_ROWS)
