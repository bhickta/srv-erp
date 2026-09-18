import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from srv_erp.masters.dynamic_item.brand_rules import validate_global_value
from srv_erp.masters.dynamic_item.configuration import are_brand_variant_rules_enabled


class DynamicVariantProfile(Document):
	def validate(self):
		template = frappe.db.get_value(
			"Item",
			self.item_template,
			["has_variants", "variant_based_on"],
			as_dict=True,
		)
		if not template or not cint(template.has_variants) or template.variant_based_on != "Item Attribute":
			frappe.throw(
				_("{0} must be an Item Attribute-based template.").format(frappe.bold(self.item_template))
			)

		attributes = [row.item_attribute for row in self.get("attributes") or [] if row.item_attribute]
		if len(attributes) != len(set(attributes)):
			frappe.throw(_("Variant Parameters cannot contain duplicate Item Attributes."))
		DynamicVariantProfile.validate_override_values(self, set(attributes))

		template_doc = frappe.get_doc("Item", self.item_template)
		template_attributes = {row.attribute for row in template_doc.get("attributes") or []}
		template_changed = False
		for row in self.get("attributes") or []:
			if row.item_attribute in template_attributes:
				continue
			if cint(frappe.db.get_value("Item Attribute", row.item_attribute, "numeric_values")):
				frappe.throw(
					_(
						"Numeric attribute {0} must be configured with its range on Item template {1} first."
					).format(frappe.bold(row.item_attribute), frappe.bold(self.item_template))
				)
			template_doc.append("attributes", {"attribute": row.item_attribute, "numeric_values": 0})
			template_attributes.add(row.item_attribute)
			template_changed = True

		if template_changed:
			template_doc.flags.dont_update_variants = True
			template_doc.save(ignore_permissions=True)

		for row in self.get("attributes") or []:
			if not cint(row.required_parameter):
				continue
			if (
				getattr(self, "configuration_mode", None) == "Template Override"
				and are_brand_variant_rules_enabled()
			):
				continue
			missing_count = frappe.db.sql(
				"""
				select count(*)
				from `tabItem` item
				where item.variant_of = %(template)s
					and not exists (
						select 1
						from `tabItem Variant Attribute` attribute
						where attribute.parent = item.name
							and attribute.attribute = %(attribute)s
					)
				""",
				{"template": self.item_template, "attribute": row.item_attribute},
			)[0][0]
			if missing_count:
				frappe.throw(
					_("Attribute {0} cannot be required: {1} existing variants do not contain it.").format(
						frappe.bold(row.item_attribute), missing_count
					)
				)

	def validate_override_values(self, attributes):
		values = set()
		values_by_attribute = set()
		for row in self.get("allowed_values") or []:
			if row.item_attribute not in attributes:
				frappe.throw(_("Override values must belong to a configured Variant Parameter."))
			key = (row.item_attribute, (row.attribute_value or "").casefold())
			if key in values:
				frappe.throw(_("Override Allowed Values cannot contain duplicates."))
			values.add(key)
			values_by_attribute.add(row.item_attribute)
			validate_global_value(row.item_attribute, row.attribute_value)
		if getattr(self, "configuration_mode", None) != "Template Override":
			return
		if not are_brand_variant_rules_enabled():
			return
		for attribute in attributes:
			if cint(frappe.db.get_value("Item Attribute", attribute, "numeric_values")):
				continue
			if attribute not in values_by_attribute:
				frappe.throw(
					_("Select at least one Override Allowed Value for {0}.").format(frappe.bold(attribute))
				)
