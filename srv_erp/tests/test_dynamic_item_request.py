import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.tests import IntegrationTestCase

from srv_erp.masters.dynamic_item.bulk_guard import require_bulk_variant_creation
from srv_erp.masters.dynamic_item.configuration import (
	APPROVED,
	APPROVER_ROLE,
	PENDING,
	REQUESTER_ROLE,
	clear_settings_cache,
)
from srv_erp.masters.dynamic_item.guard import validate_no_unapproved_items
from srv_erp.masters.dynamic_item.service import (
	approve_request,
	reject_request,
	resolve_or_request,
)


class TestDynamicItemRequest(IntegrationTestCase):
	REQUESTER = "dynamic.item.requester@example.com"
	APPROVER = "dynamic.item.approver@example.com"
	ATTRIBUTE = "_Test Dynamic Colour"
	TEMPLATE = "_Test Dynamic Item Template"

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._ensure_users()
		self._configure_settings()
		self._ensure_basic_masters()
		self._ensure_attribute()
		self._ensure_template_and_profile()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_variant_is_staged_disabled_and_duplicate_request_is_reused(self):
		result = self._request("_Test Dynamic Teal")

		self.assertEqual(result["outcome"], "pending_approval")
		self.assertTrue(result["created"])
		item = frappe.get_doc("Item", result["item_code"])
		self.assertEqual(item.disabled, 1)
		self.assertEqual(item.dynamic_item_approval_status, PENDING)
		self.assertEqual(item.dynamic_item_request, result["request"])
		self.assertTrue(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Dynamic Item Request",
					"reference_name": result["request"],
					"allocated_to": self.APPROVER,
					"status": "Open",
				},
			)
		)

		repeated = self._request("_Test Dynamic Teal")
		self.assertEqual(repeated["request"], result["request"])
		self.assertFalse(repeated["created"])

	def test_maker_checker_approval_enables_item_and_resolves_future_requests(self):
		result = self._request("_Test Dynamic Navy")
		request_name = result["request"]

		frappe.set_user(self.APPROVER)
		approved = approve_request(request_name)

		self.assertEqual(approved["outcome"], "approved")
		item = frappe.get_doc("Item", approved["item_code"])
		self.assertEqual(item.disabled, 0)
		self.assertEqual(item.dynamic_item_approval_status, APPROVED)
		self.assertEqual(item.dynamic_item_approved_by, self.APPROVER)
		self.assertFalse(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Dynamic Item Request",
					"reference_name": request_name,
					"status": "Open",
				},
			)
		)

		frappe.set_user(self.REQUESTER)
		existing = resolve_or_request(self._payload("_Test Dynamic Navy"))
		self.assertEqual(existing["outcome"], "existing")
		self.assertEqual(existing["item_code"], approved["item_code"])

	def test_requester_cannot_approve_own_request(self):
		frappe.set_user(self.REQUESTER)
		frappe.get_doc("User", self.REQUESTER).add_roles(APPROVER_ROLE)
		result = resolve_or_request(self._payload("_Test Dynamic Amber"))

		with self.assertRaises(frappe.PermissionError):
			approve_request(result["request"])

	def test_pending_item_is_blocked_from_transaction(self):
		result = self._request("_Test Dynamic Silver")
		material_request = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"items": [{"item_code": result["item_code"], "qty": 1}],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			validate_no_unapproved_items(material_request)

	def test_rejection_deletes_staged_item_and_request_only_schema(self):
		attribute = "_Test Dynamic Request Only Finish"
		frappe.set_user(self.REQUESTER)
		result = resolve_or_request(
			{
				"template_item": self.TEMPLATE,
				"attributes": {self.ATTRIBUTE: "_Test Dynamic Red", attribute: "Matte"},
			}
		)
		item_code = result["item_code"]

		frappe.set_user(self.APPROVER)
		rejected = reject_request(result["request"], "Not an approved finish")

		self.assertEqual(rejected["outcome"], "rejected")
		self.assertFalse(frappe.db.exists("Item", item_code))
		self.assertFalse(frappe.db.exists("Item Attribute", attribute))
		self.assertFalse(
			frappe.db.exists(
				"Item Variant Attribute",
				{"parent": self.TEMPLATE, "attribute": attribute},
			)
		)

	def test_last_rejection_cleans_schema_shared_by_pending_requests(self):
		attribute = "_Test Dynamic Shared Finish"
		frappe.set_user(self.REQUESTER)
		first = resolve_or_request(
			{
				"template_item": self.TEMPLATE,
				"attributes": {self.ATTRIBUTE: "_Test Dynamic First", attribute: "Satin"},
			}
		)
		second = resolve_or_request(
			{
				"template_item": self.TEMPLATE,
				"attributes": {self.ATTRIBUTE: "_Test Dynamic Second", attribute: "Satin"},
			}
		)

		frappe.set_user(self.APPROVER)
		reject_request(first["request"], "Reject first")
		self.assertTrue(frappe.db.exists("Item Attribute", attribute))
		self.assertTrue(frappe.db.exists("Item", second["item_code"]))

		reject_request(second["request"], "Reject second")
		self.assertFalse(frappe.db.exists("Item Attribute", attribute))
		self.assertFalse(
			frappe.db.exists(
				"Item Variant Attribute",
				{"parent": self.TEMPLATE, "attribute": attribute},
			)
		)

	def test_dynamic_brand_is_staged_and_removed_on_rejection(self):
		brand = "_Test Dynamic Request Brand"
		frappe.set_user(self.REQUESTER)
		result = resolve_or_request(
			{
				"template_item": self.TEMPLATE,
				"attributes": {self.ATTRIBUTE: "_Test Dynamic Brand Colour", "Brand": brand},
			}
		)
		self.assertTrue(frappe.db.exists("Brand", brand))
		self.assertTrue(
			frappe.db.exists(
				"Item Attribute Value",
				{"parent": "Brand", "attribute_value": brand},
			)
		)

		frappe.set_user(self.APPROVER)
		reject_request(result["request"], "Brand not approved")
		self.assertFalse(frappe.db.exists("Brand", brand))
		self.assertFalse(
			frappe.db.exists(
				"Item Attribute Value",
				{"parent": "Brand", "attribute_value": brand},
			)
		)

	def test_packaging_is_a_separate_approval_without_new_item_identity(self):
		result = self._request("_Test Dynamic Violet")
		frappe.set_user(self.APPROVER)
		approved = approve_request(result["request"])

		frappe.set_user(self.REQUESTER)
		packaging = resolve_or_request(
			self._payload(
				"_Test Dynamic Violet",
				uoms=[{"uom": "Box", "conversion_factor": 12}],
			)
		)
		self.assertEqual(packaging["outcome"], "packaging_approval_required")
		self.assertEqual(packaging["item_code"], approved["item_code"])

		frappe.set_user(self.APPROVER)
		approve_request(packaging["request"])
		conversion_factor = frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": approved["item_code"], "uom": "Box"},
			"conversion_factor",
		)
		self.assertEqual(conversion_factor, 12)

	def test_direct_and_bulk_variant_creation_are_blocked(self):
		variant = create_variant(self.TEMPLATE, {self.ATTRIBUTE: "_Test Dynamic Red"})
		with self.assertRaises(frappe.PermissionError):
			variant.insert()

		with self.assertRaises(frappe.ValidationError):
			require_bulk_variant_creation()

	def test_invalid_and_overlapping_packaging_requests_are_blocked(self):
		result = self._request("_Test Dynamic Copper")
		frappe.set_user(self.APPROVER)
		approve_request(result["request"])

		frappe.set_user(self.REQUESTER)
		with self.assertRaises(frappe.ValidationError):
			resolve_or_request(
				self._payload(
					"_Test Dynamic Copper",
					uoms=[{"uom": "Box", "conversion_factor": "NaN"}],
				)
			)

		first = resolve_or_request(
			self._payload(
				"_Test Dynamic Copper",
				uoms=[{"uom": "Box", "conversion_factor": 12}],
			)
		)
		repeated = resolve_or_request(
			self._payload(
				"_Test Dynamic Copper",
				uoms=[{"uom": "Box", "conversion_factor": 12}],
			)
		)
		self.assertEqual(repeated["request"], first["request"])
		self.assertFalse(repeated["created"])

		with self.assertRaises(frappe.ValidationError):
			resolve_or_request(
				self._payload(
					"_Test Dynamic Copper",
					uoms=[{"uom": "Box", "conversion_factor": 24}],
				)
			)

	def test_existing_variant_resolves_without_an_available_approver(self):
		result = self._request("_Test Dynamic Existing")
		frappe.set_user(self.APPROVER)
		approved = approve_request(result["request"])
		frappe.db.set_value("User", self.APPROVER, "enabled", 0)

		frappe.set_user(self.REQUESTER)
		existing = resolve_or_request(self._payload("_Test Dynamic Existing"))
		self.assertEqual(existing["outcome"], "existing")
		self.assertEqual(existing["item_code"], approved["item_code"])

		with self.assertRaises(frappe.ValidationError):
			resolve_or_request(self._payload("_Test Dynamic Needs Approver"))

	def _request(self, value):
		frappe.set_user(self.REQUESTER)
		return resolve_or_request(self._payload(value))

	def _payload(self, value, uoms=None):
		return {
			"template_item": self.TEMPLATE,
			"attributes": {self.ATTRIBUTE: value},
			"uoms": uoms or [],
		}

	def _configure_settings(self):
		settings = frappe.get_single("Masters Settings")
		settings.enable_dynamic_item_requests = 1
		settings.enforce_variant_approval = 1
		settings.allow_bulk_variant_creation = 0
		settings.allow_dynamic_attributes = 1
		settings.approver_role = APPROVER_ROLE
		settings.set("requester_roles", [])
		settings.append("requester_roles", {"role": REQUESTER_ROLE})
		settings.save(ignore_permissions=True)
		clear_settings_cache()

	def _ensure_users(self):
		self._ensure_user(self.REQUESTER, [REQUESTER_ROLE, "Stock User"])
		self._ensure_user(self.APPROVER, [APPROVER_ROLE, "Stock User"])

	def _ensure_user(self, email, roles):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@", 1)[0],
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("User", email, "enabled", 1)
		user = frappe.get_doc("User", email)
		missing_roles = [role for role in roles if role not in frappe.get_roles(email)]
		if missing_roles:
			user.add_roles(*missing_roles)

	def _ensure_attribute(self):
		if frappe.db.exists("Item Attribute", self.ATTRIBUTE):
			return
		attribute = frappe.get_doc(
			{"doctype": "Item Attribute", "attribute_name": self.ATTRIBUTE, "numeric_values": 0}
		)
		attribute.append(
			"item_attribute_values",
			{"attribute_value": "_Test Dynamic Red", "abbr": "RED"},
		)
		attribute.insert(ignore_permissions=True)

	def _ensure_template_and_profile(self):
		if not frappe.db.exists("Item", self.TEMPLATE):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": self.TEMPLATE,
					"item_name": self.TEMPLATE,
					"item_group": "_Test Dynamic Item Group",
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"has_variants": 1,
					"variant_based_on": "Item Attribute",
					"attributes": [{"attribute": self.ATTRIBUTE}],
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Dynamic Variant Profile", self.TEMPLATE):
			profile = frappe.get_doc(
				{
					"doctype": "Dynamic Variant Profile",
					"item_template": self.TEMPLATE,
					"enabled": 1,
				}
			)
			profile.append(
				"attributes",
				{
					"item_attribute": self.ATTRIBUTE,
					"required_parameter": 1,
					"allow_new_values": 1,
				},
			)
			profile.insert(ignore_permissions=True)

	def _ensure_basic_masters(self):
		for uom in ("Nos", "Box"):
			if not frappe.db.exists("UOM", uom):
				frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
		if not frappe.db.exists("Item Group", "_Test Dynamic Item Group"):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "_Test Dynamic Item Group",
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
