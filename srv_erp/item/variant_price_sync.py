import frappe
from frappe import _


PRICE_FIELDS = (
	"price_list",
	"uom",
	"packing_unit",
	"price_list_rate",
	"valid_from",
	"valid_upto",
	"lead_time_days",
	"customer",
	"supplier",
	"note",
)

PRICE_IDENTITY_FIELDS = (
	"price_list",
	"uom",
	"packing_unit",
	"valid_from",
	"valid_upto",
	"customer",
	"supplier",
	"batch_no",
)


class TemplateItemPriceMixin:
	"""Allow an Item Price to act as the master price for a variant template."""

	def validate_item_template(self):
		is_template = bool(frappe.get_cached_value("Item", self.item_code, "has_variants"))
		previous = self.get_doc_before_save()
		if previous and previous.get("is_variant_price_template") and previous.item_code != self.item_code:
			frappe.throw(_("The item cannot be changed on a master variant price. Create a new Item Price instead."))
		self.is_variant_price_template = is_template
		if not is_template:
			return super().validate_item_template()
		if self.batch_no:
			frappe.throw(_("A template Item Price cannot be restricted to a batch. Create a variant-specific price instead."))


def protect_managed_variant_price(doc, method=None):
	previous = doc.get_doc_before_save()
	source_name = doc.get("variant_price_template") or (previous and previous.get("variant_price_template"))
	if not source_name or doc.flags.get("variant_price_sync"):
		return

	frappe.throw(
		_("This Item Price is managed by template price {0}. Update the template price instead.").format(
			frappe.bold(source_name)
		)
	)


def sync_template_price_to_variants(doc, method=None):
	if not doc.get("is_variant_price_template") or doc.get("variant_price_template"):
		return

	variant_names = frappe.get_all(
		"Item",
		filters={"variant_of": doc.item_code},
		pluck="name",
		order_by="name",
	)
	_sync_source_to_variants(doc, variant_names)


def sync_prices_to_new_variant(doc, method=None):
	if not doc.variant_of or doc.has_variants:
		return

	source_names = frappe.get_all(
		"Item Price",
		filters={"item_code": doc.variant_of, "is_variant_price_template": 1},
		pluck="name",
	)
	for source_name in source_names:
		_sync_source_to_variants(frappe.get_doc("Item Price", source_name), [doc.name])


def _sync_source_to_variants(source, variant_names):
	if not variant_names:
		return

	prices = frappe.get_all(
			"Item Price",
		filters={"item_code": ["in", variant_names], "price_list": source.price_list},
		fields=["name", "item_code", "variant_price_template", *PRICE_IDENTITY_FIELDS],
	)
	existing = {row.item_code: row.name for row in prices if row.variant_price_template == source.name}
	adoptable = {
		row.item_code: row.name
		for row in prices
		if not row.variant_price_template and _price_identity(row) == _price_identity(source)
	}

	for item_code in variant_names:
		price_name = existing.get(item_code) or adoptable.get(item_code)
		managed_price = (
			frappe.get_doc("Item Price", price_name)
			if price_name
			else frappe.new_doc("Item Price")
		)
		managed_price.flags.variant_price_sync = True
		managed_price.item_code = item_code
		managed_price.variant_price_template = source.name
		for fieldname in PRICE_FIELDS:
			managed_price.set(fieldname, source.get(fieldname))

		if managed_price.is_new():
			managed_price.insert()
		else:
			managed_price.save()


def _price_identity(price):
	return tuple(_normalise_identity_value(fieldname, price.get(fieldname)) for fieldname in PRICE_IDENTITY_FIELDS)


def _normalise_identity_value(fieldname, value):
	if fieldname == "packing_unit":
		return value or 0
	return value or None


def delete_managed_variant_prices(doc, method=None):
	if doc.get("variant_price_template") and not doc.flags.get("variant_price_sync"):
		frappe.throw(
			_("This Item Price is managed by a template and cannot be deleted directly. Delete the template price instead.")
		)

	if not doc.get("is_variant_price_template"):
		return

	for name in frappe.get_all(
		"Item Price", filters={"variant_price_template": doc.name}, pluck="name"
	):
		managed_price = frappe.get_doc("Item Price", name)
		managed_price.flags.variant_price_sync = True
		managed_price.delete()
