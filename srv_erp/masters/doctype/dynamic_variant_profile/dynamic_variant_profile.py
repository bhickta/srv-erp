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
					).format(
						frappe.bold(row.item_attribute), frappe.bold(self.item_template)
					)
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
