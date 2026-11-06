from __future__ import annotations

import frappe
from frappe.utils import flt

from srv_erp.package_barcode.service import parse_barcode_conversion_factor

TRANSACTION_TABLES = (
	"tabDelivery Note Item",
	"tabStock Entry Detail",
	"tabSales Order Item",
	"tabPurchase Receipt Item",
	"tabPurchase Order Item",
	"tabSales Invoice Item",
	"tabPurchase Invoice Item",
)


def execute():
	_set_factors_from_item_uoms()
	_set_factors_from_barcode_suffix()
	_set_factors_from_transactions()
	_backfill_scan_factors()

	unresolved = frappe.db.sql(
		"select count(*) from `tabPackage Barcode` where ifnull(conversion_factor, 0) = 0"
	)[0][0]
	if unresolved:
		frappe.logger().warning(
			"Could not backfill conversion factors for {0} Package Barcode records.".format(unresolved)
		)


def _set_factors_from_item_uoms():
	frappe.db.sql(
		"""
		update `tabPackage Barcode` barcode
		inner join `tabItem` item on item.name = barcode.item_code
		set barcode.conversion_factor = 1
		where ifnull(barcode.conversion_factor, 0) = 0
			and barcode.uom = item.stock_uom
		"""
	)
	frappe.db.sql(
		"""
		update `tabPackage Barcode` barcode
		inner join `tabUOM Conversion Detail` uom on uom.parent = barcode.item_code
			and uom.uom = barcode.uom
		set barcode.conversion_factor = uom.conversion_factor
		where ifnull(barcode.conversion_factor, 0) = 0
			and ifnull(uom.conversion_factor, 0) > 0
		"""
	)


def _set_factors_from_barcode_suffix():
	unresolved_pairs = _get_unresolved_pairs()
	if not unresolved_pairs:
		return

	rows = frappe.db.sql(
		"""
		select barcode, item_code, uom
		from `tabPackage Barcode`
		where ifnull(conversion_factor, 0) = 0
		""",
		as_dict=True,
	)
	factors_by_pair: dict[tuple[str, str], set[float]] = {}
	for row in rows:
		conversion_factor = parse_barcode_conversion_factor(row.barcode)
		if conversion_factor > 0:
			factors_by_pair.setdefault((row.item_code, row.uom), set()).add(conversion_factor)

	for pair, factors in factors_by_pair.items():
		if pair not in unresolved_pairs or len(factors) != 1:
			continue
		_update_pair(pair[0], pair[1], factors.pop())


def _set_factors_from_transactions():
	unresolved_pairs = _get_unresolved_pairs()
	if not unresolved_pairs:
		return

	item_codes = sorted({item_code for item_code, _uom in unresolved_pairs})
	selects = [
		f"""
		select item_code, uom, conversion_factor, modified
		from `{table}`
		where item_code in %(items)s
			and ifnull(conversion_factor, 0) > 0
			and ifnull(uom, '') != ''
		"""
		for table in TRANSACTION_TABLES
	]
	rows = frappe.db.sql(
		"""
		select item_code, uom,
			substring_index(group_concat(conversion_factor order by modified desc), ',', 1)
				as conversion_factor
		from ({0}) history
		group by item_code, uom
		""".format(" union all ".join(selects)),
		{"items": item_codes},
		as_dict=True,
	)

	for row in rows:
		if (row.item_code, row.uom) not in unresolved_pairs:
			continue
		conversion_factor = flt(row.conversion_factor)
		if conversion_factor > 0:
			_update_pair(row.item_code, row.uom, conversion_factor)


def _backfill_scan_factors():
	frappe.db.sql(
		"""
		update `tabPackage Barcode Scan` scan
		inner join `tabPackage Barcode` barcode on barcode.name = scan.package_barcode
		set scan.conversion_factor = barcode.conversion_factor
		where ifnull(scan.conversion_factor, 0) = 0
			and ifnull(barcode.conversion_factor, 0) > 0
		"""
	)


def _get_unresolved_pairs() -> set[tuple[str, str]]:
	return {
		(row.item_code, row.uom)
		for row in frappe.db.sql(
			"""
			select distinct item_code, uom
			from `tabPackage Barcode`
			where ifnull(conversion_factor, 0) = 0
				and ifnull(item_code, '') != ''
				and ifnull(uom, '') != ''
			""",
			as_dict=True,
		)
	}


def _update_pair(item_code: str, uom: str, conversion_factor: float):
	frappe.db.sql(
		"""
		update `tabPackage Barcode`
		set conversion_factor = %(conversion_factor)s
		where item_code = %(item_code)s
			and uom = %(uom)s
			and ifnull(conversion_factor, 0) = 0
		""",
		{
			"conversion_factor": conversion_factor,
			"item_code": item_code,
			"uom": uom,
		},
	)
