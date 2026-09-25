import frappe
from frappe.model.document import Document


class BrandVariantProfile(Document):
	def validate(self):
		from srv_erp.masters.dynamic_item.brand_rules import update_profile_publication_state

		update_profile_publication_state(self)

	def on_trash(self):
		from frappe import _

		from srv_erp.masters.dynamic_item.brand_rules import get_published_configuration

		if get_published_configuration(self):
			frappe.throw(
				_(
					"Remove the published Brand configuration through the draft and publish the change before deleting this profile."
				)
			)
