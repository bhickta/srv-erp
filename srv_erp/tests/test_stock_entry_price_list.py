from unittest import TestCase
from unittest.mock import patch

from srv_erp.stock.stock_entry import SRVStockEntry, get_stock_entry_price_list_rate


class AttrDict(dict):
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__


class TestStockEntryPriceList(TestCase):
	@patch("srv_erp.stock.stock_entry._", side_effect=lambda message: message)
	@patch("srv_erp.stock.stock_entry.frappe.bold", side_effect=lambda value: value)
	@patch("srv_erp.stock.stock_entry.frappe.throw", side_effect=RuntimeError)
	@patch("srv_erp.stock.stock_entry.get_price_list_rate_for", return_value=None)
	@patch("srv_erp.stock.stock_entry.frappe.get_cached_value")
	def test_missing_item_price_stops_the_stock_entry(
		self,
		get_cached_value,
		_get_price_list_rate_for,
		throw,
		_bold,
		_translate,
	):
		get_cached_value.side_effect = [
			AttrDict(currency="INR", price_not_uom_dependent=0),
			None,
		]

		with self.assertRaises(RuntimeError):
			get_stock_entry_price_list_rate("ITEM-1", "Stock Rates", "Nos", 1, "2026-09-15", "SRV")

		self.assertEqual(throw.call_args.kwargs["title"], "Stock Entry Price Missing")

	@patch("srv_erp.stock.stock_entry.get_exchange_rate")
	@patch("srv_erp.stock.stock_entry.erpnext.get_company_currency", return_value="INR")
	@patch("srv_erp.stock.stock_entry.get_price_list_rate_for", return_value=125)
	@patch("srv_erp.stock.stock_entry.frappe.get_cached_value")
	def test_price_lookup_uses_stock_uom_date_quantity_and_currency(
		self, get_cached_value, get_price_list_rate_for, _get_company_currency, get_exchange_rate
	):
		get_cached_value.return_value = AttrDict(currency="USD", price_not_uom_dependent=0)
		get_exchange_rate.return_value = 83

		rate = get_stock_entry_price_list_rate(
			item_code="ITEM-1",
			price_list="Stock Rates",
			stock_uom="Nos",
			qty=3,
			posting_date="2026-09-15",
			company="SRV",
			batch_no="BATCH-1",
		)

		args = get_price_list_rate_for.call_args.args[0]
		self.assertEqual(
			(args.price_list, args.uom, args.qty, args.transaction_date, args.batch_no),
			("Stock Rates", "Nos", 3, "2026-09-15", "BATCH-1"),
		)
		self.assertEqual(rate, 10375)
		get_exchange_rate.assert_called_once_with("USD", "INR", "2026-09-15")

	@patch("srv_erp.stock.stock_entry.get_exchange_rate")
	@patch("srv_erp.stock.stock_entry.erpnext.get_company_currency", return_value="INR")
	@patch("srv_erp.stock.stock_entry.get_price_list_rate_for", side_effect=[None, 90])
	@patch("srv_erp.stock.stock_entry.frappe.get_cached_value")
	def test_price_lookup_falls_back_to_variant_template(
		self, get_cached_value, get_price_list_rate_for, _get_company_currency, get_exchange_rate
	):
		get_cached_value.side_effect = [
			AttrDict(currency="INR", price_not_uom_dependent=0),
			"ITEM-TEMPLATE",
		]

		rate = get_stock_entry_price_list_rate("ITEM-VARIANT", "Stock Rates", "Nos", 1, "2026-09-15", "SRV")

		self.assertEqual(rate, 90)
		self.assertEqual(
			[price_call.args[1] for price_call in get_price_list_rate_for.call_args_list],
			["ITEM-VARIANT", "ITEM-TEMPLATE"],
		)
		get_exchange_rate.assert_not_called()

	@patch("erpnext.stock.doctype.stock_entry.stock_entry.StockEntry.set_basic_rate")
	@patch("srv_erp.stock.stock_entry.get_stock_entry_price_list_rate", return_value=75)
	@patch("srv_erp.stock.stock_entry.get_configured_price_list", return_value="Stock Rates")
	def test_configured_list_updates_only_eligible_incoming_rows(
		self, _get_price_list, get_rate, base_set_basic_rate
	):
		incoming = self.make_item(t_warehouse="Stores - S", transfer_qty=2)
		outgoing = self.make_item(s_warehouse="Stores - S", transfer_qty=3, basic_rate=40)
		zero_rate = self.make_item(
			t_warehouse="Stores - S", transfer_qty=4, allow_zero_valuation_rate=1, basic_rate=0
		)
		manual = self.make_item(
			t_warehouse="Stores - S", transfer_qty=5, set_basic_rate_manually=1, basic_rate=22
		)
		doc = object.__new__(SRVStockEntry)
		doc.__dict__.update(
			{
				"posting_date": "2026-09-15",
				"company": "SRV",
				"items": [incoming, outgoing, zero_rate, manual],
			}
		)

		SRVStockEntry.set_basic_rate(doc)

		base_set_basic_rate.assert_called_once_with(True, True)
		get_rate.assert_called_once()
		self.assertEqual((incoming.basic_rate, incoming.basic_amount), (75, 150))
		self.assertEqual((outgoing.basic_rate, zero_rate.basic_rate, manual.basic_rate), (40, 0, 22))

	@patch("srv_erp.stock.stock_entry.get_configured_price_list", return_value=None)
	@patch("erpnext.stock.doctype.stock_entry.stock_entry.StockEntry.set_basic_rate")
	def test_empty_setting_keeps_standard_rate_calculation(self, base_set_basic_rate, _get_price_list):
		doc = object.__new__(SRVStockEntry)
		doc.__dict__["items"] = []

		SRVStockEntry.set_basic_rate(doc, reset_outgoing_rate=False, raise_error_if_no_rate=False)

		base_set_basic_rate.assert_called_once_with(False, False)

	@staticmethod
	def make_item(**values):
		defaults = {
			"item_code": "ITEM-1",
			"stock_uom": "Nos",
			"s_warehouse": None,
			"t_warehouse": None,
			"transfer_qty": 1,
			"basic_rate": 0,
			"basic_amount": 0,
			"batch_no": None,
			"allow_zero_valuation_rate": 0,
			"set_basic_rate_manually": 0,
		}
		defaults.update(values)
		item = AttrDict(defaults)
		item.precision = lambda _fieldname: None
		return item
