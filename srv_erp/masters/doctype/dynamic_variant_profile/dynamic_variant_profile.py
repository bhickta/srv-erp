import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


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

		for row in self.get("attributes") or []:
			is_attached = frappe.db.exists(
				"Item Variant Attribute",
				{"parent": self.item_template, "attribute": row.item_attribute},
			)
			if (
				cint(frappe.db.get_value("Item Attribute", row.item_attribute, "numeric_values"))
				and not is_attached
			):
				frappe.throw(
					_("Numeric attribute {0} must be configured on the template first.").format(
						frappe.bold(row.item_attribute)
					)
				)
			if not cint(row.required_parameter):
				continue
			if not is_attached:
				frappe.throw(
					_("Required attribute {0} is not attached to template {1}.").format(
						frappe.bold(row.item_attribute), frappe.bold(self.item_template)
					)
				)
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
