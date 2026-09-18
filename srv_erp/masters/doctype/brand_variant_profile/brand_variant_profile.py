from frappe.model.document import Document


class BrandVariantProfile(Document):
	def validate(self):
		from srv_erp.masters.dynamic_item.brand_rules import update_profile_publication_state

		update_profile_publication_state(self)
