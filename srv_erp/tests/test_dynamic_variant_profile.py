import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from srv_erp.masters.doctype.dynamic_variant_profile.dynamic_variant_profile import (
	DynamicVariantProfile,
)


class TestDynamicVariantProfile(unittest.TestCase):
	@patch("srv_erp.masters.doctype.dynamic_variant_profile.dynamic_variant_profile.frappe")
	def test_existing_categorical_profile_attribute_is_attached_to_template(self, frappe):
		profile_row = SimpleNamespace(item_attribute="Box", required_parameter=0)
		profile = SimpleNamespace(
			item_template="VS 1103",
			get=lambda fieldname: [profile_row] if fieldname == "attributes" else None,
		)
		template = MagicMock()
		template.get.return_value = []
		frappe.db.get_value.side_effect = [
			SimpleNamespace(has_variants=1, variant_based_on="Item Attribute"),
			0,
		]
		frappe.get_doc.return_value = template

		DynamicVariantProfile.validate(profile)

		template.append.assert_called_once_with(
			"attributes", {"attribute": "Box", "numeric_values": 0}
		)
		self.assertTrue(template.flags.dont_update_variants)
		template.save.assert_called_once_with(ignore_permissions=True)

	@patch(
		"srv_erp.masters.doctype.dynamic_variant_profile.dynamic_variant_profile._",
		side_effect=lambda message: message,
	)
	@patch("srv_erp.masters.doctype.dynamic_variant_profile.dynamic_variant_profile.frappe")
	def test_unattached_numeric_attribute_requires_template_range(self, frappe, _translate):
		profile_row = SimpleNamespace(item_attribute="Length", required_parameter=0)
		profile = SimpleNamespace(
			item_template="VS 1103",
			get=lambda fieldname: [profile_row] if fieldname == "attributes" else None,
		)
		template = MagicMock()
		template.get.return_value = []
		frappe.db.get_value.side_effect = [
			SimpleNamespace(has_variants=1, variant_based_on="Item Attribute"),
			1,
		]
		frappe.get_doc.return_value = template
		frappe.bold.side_effect = lambda value: value
		frappe.throw.side_effect = RuntimeError

		with self.assertRaises(RuntimeError):
			DynamicVariantProfile.validate(profile)

		template.append.assert_not_called()
		template.save.assert_not_called()
