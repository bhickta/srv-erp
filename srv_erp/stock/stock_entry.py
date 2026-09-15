import erpnext
import frappe
from erpnext.setup.utils import get_exchange_rate
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.get_item_details import get_price_list_rate_for
from frappe import _
from frappe.utils import flt

PRICE_LIST_SETTING = "stock_entry_price_list"


def get_configured_price_list():
	return frappe.db.get_single_value("SRV Settings", PRICE_LIST_SETTING)


def get_stock_entry_price_list_rate(
	item_code,
	price_list,
	stock_uom,
	qty,
	posting_date,
	company,
	batch_no=None,
):
	price_list_details = frappe.get_cached_value(
		"Price List",
		price_list,
		["currency", "price_not_uom_dependent"],
		as_dict=True,
	)
	args = frappe._dict(
		{
			"price_list": price_list,
			"uom": stock_uom,
			"stock_uom": stock_uom,
			"conversion_factor": 1,
			"transaction_date": posting_date,
			"qty": abs(flt(qty)),
			"batch_no": batch_no,
			"price_list_uom_dependant": (price_list_details or {}).get("price_not_uom_dependent"),
		}
	)

	rate = get_price_list_rate_for(args, item_code)
	if rate is None:
		variant_of = frappe.get_cached_value("Item", item_code, "variant_of")
		if variant_of:
			rate = get_price_list_rate_for(args, variant_of)

	if rate is None:
		frappe.throw(
			_("No valid Item Price was found for Item {0} in Price List {1} on {2}.").format(
				frappe.bold(item_code),
				frappe.bold(price_list),
				frappe.bold(posting_date),
			),
			title=_("Stock Entry Price Missing"),
		)

	company_currency = erpnext.get_company_currency(company)
	price_list_currency = (price_list_details or {}).get("currency") or company_currency
	if price_list_currency != company_currency:
		exchange_rate = get_exchange_rate(price_list_currency, company_currency, posting_date)
		if not exchange_rate:
			frappe.throw(
				_("Exchange Rate is required from {0} to {1} for Stock Entry Price List {2}.").format(
					frappe.bold(price_list_currency),
					frappe.bold(company_currency),
					frappe.bold(price_list),
				),
				title=_("Stock Entry Exchange Rate Missing"),
			)
		rate *= exchange_rate

	return flt(rate)


@frappe.whitelist()
def get_configured_stock_entry_rate(
	item_code,
	stock_uom,
	qty,
	posting_date,
	company,
	batch_no=None,
):
	price_list = get_configured_price_list()
	if not price_list:
		return None

	return {
		"price_list": price_list,
		"rate": get_stock_entry_price_list_rate(
			item_code=item_code,
			price_list=price_list,
			stock_uom=stock_uom,
			qty=qty,
			posting_date=posting_date,
			company=company,
			batch_no=batch_no,
		),
	}


class SRVStockEntry(StockEntry):
	def set_basic_rate(self, reset_outgoing_rate=True, raise_error_if_no_rate=True):
		super().set_basic_rate(reset_outgoing_rate, raise_error_if_no_rate)

		price_list = get_configured_price_list()
		if not price_list:
			return

		for item in self.get("items"):
			if (
				item.s_warehouse
				or not item.t_warehouse
				or item.allow_zero_valuation_rate
				or item.set_basic_rate_manually
			):
				continue

			item.basic_rate = get_stock_entry_price_list_rate(
				item_code=item.item_code,
				price_list=price_list,
				stock_uom=item.stock_uom,
				qty=item.transfer_qty,
				posting_date=self.posting_date,
				company=self.company,
				batch_no=item.batch_no,
			)
			item.basic_amount = flt(
				flt(item.transfer_qty) * flt(item.basic_rate),
				item.precision("basic_amount"),
			)
