from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from srv_erp.masters.dynamic_item.configuration import ADD_PACKAGING, PENDING
from srv_erp.masters.dynamic_item.exceptions import DynamicItemConflict


def get_missing_packaging(item, uoms: list[dict]) -> list[dict]:
	existing = {row.uom: flt(row.conversion_factor) for row in item.get("uoms") or [] if row.uom}
	missing = []
	for row in uoms:
		uom = row["uom"]
		factor = flt(row["conversion_factor"])
		if uom in existing:
			if flt(existing[uom], 9) != flt(factor, 9):
				frappe.throw(
					_(
						"UOM {0} already has conversion factor {1}; requested factor {2} is a conflict."
					).format(frappe.bold(uom), existing[uom], factor),
					DynamicItemConflict,
				)
			continue
		if uom == item.stock_uom:
			if flt(factor, 9) != 1:
				frappe.throw(_("Stock UOM {0} must have conversion factor 1.").format(frappe.bold(uom)))
			continue
		missing.append({"uom": uom, "conversion_factor": factor})
	return missing


def validate_no_overlapping_packaging_request(item_code: str, uoms: list[dict]):
	requested_uoms = {row["uom"] for row in uoms}
	if not requested_uoms:
		return
	rows = frappe.db.sql(
		"""
		select request.name, packaging.uom
		from `tabDynamic Item Request` request
		inner join `tabDynamic Item Request UOM` packaging on packaging.parent = request.name
		where request.request_type = %(request_type)s
			and request.status = %(status)s
			and request.resolved_item = %(item_code)s
			and packaging.uom in %(uoms)s
		order by request.creation
		limit 1
		""",
		{
			"request_type": ADD_PACKAGING,
			"status": PENDING,
			"item_code": item_code,
			"uoms": tuple(requested_uoms),
		},
		as_dict=True,
	)
	if rows:
		frappe.throw(
			_("UOM {0} already has a pending packaging request {1} for Item {2}.").format(
				frappe.bold(rows[0].uom),
				frappe.get_desk_link("Dynamic Item Request", rows[0].name),
				frappe.bold(item_code),
			),
			DynamicItemConflict,
		)


def add_packaging_rows(item, uoms: list[dict]):
	missing = get_missing_packaging(item, uoms)
	for row in missing:
		item.append(
			"uoms",
			{"uom": row["uom"], "conversion_factor": row["conversion_factor"]},
		)
	return len(missing)
