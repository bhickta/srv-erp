import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint


MAPPED_USER_FIELD = "sales_user"
MANAGED_PERMISSION_FIELD = "srv_sales_person_mapping"


def create_sales_person_user_mapping_fields():
	create_custom_fields(
		{
			"Sales Person": [
				{
					"description": "User mapped to this Sales Person. A default User Permission is maintained automatically for this mapping.",
					"fieldname": MAPPED_USER_FIELD,
					"fieldtype": "Link",
					"insert_after": "employee",
					"label": "Mapped User",
					"options": "User",
				},
			],
			"Customer": [
				{
					"description": "Primary Sales Person for this customer.",
					"fieldname": "sales_person",
					"fieldtype": "Link",
					"insert_after": "account_manager",
					"label": "Sales Person",
					"options": "Sales Person",
				},
			],
			"User Permission": [
				{
					"default": "0",
					"fieldname": MANAGED_PERMISSION_FIELD,
					"fieldtype": "Check",
					"hidden": 1,
					"insert_after": "is_default",
					"label": "Managed by Sales Person Mapping",
					"no_copy": 1,
				},
			],
		},
		update=True,
	)


def validate_sales_person_user_mapping(doc, method=None):
	user = doc.get(MAPPED_USER_FIELD)
	if not user:
		return

	existing_sales_person = frappe.db.get_value(
		"Sales Person",
		{
			MAPPED_USER_FIELD: user,
			"name": ["!=", doc.name],
		},
		"name",
	)
	if existing_sales_person:
		frappe.throw(
			_("User {0} is already mapped to Sales Person {1}.").format(
				frappe.bold(user),
				frappe.bold(existing_sales_person),
			)
		)


def sync_sales_person_user_permission(doc, method=None):
	sync_user_permission_for_sales_person(doc.name)


def delete_sales_person_user_permission(doc, method=None):
	delete_managed_user_permissions(doc.name)


def sync_all_sales_person_user_permissions():
	create_sales_person_user_mapping_fields()
	for sales_person in frappe.get_all(
		"Sales Person",
		fields=["name", MAPPED_USER_FIELD, "enabled"],
	):
		sync_user_permission_for_sales_person(
			sales_person.name,
			user=sales_person.get(MAPPED_USER_FIELD),
			enabled=cint(sales_person.enabled),
		)


def sync_user_permission_for_sales_person(sales_person, user=None, enabled=None):
	if user is None:
		user = frappe.db.get_value("Sales Person", sales_person, MAPPED_USER_FIELD)
	if enabled is None:
		enabled = cint(frappe.db.get_value("Sales Person", sales_person, "enabled"))

	delete_managed_user_permissions(sales_person, keep_user=user if user and enabled else None)

	if not user or not enabled:
		return

	if not frappe.db.exists("User", user):
		return

	permission_name = frappe.db.exists(
		"User Permission",
		{
			"user": user,
			"allow": "Sales Person",
			"for_value": sales_person,
			"applicable_for": ["is", "not set"],
		},
	)

	if permission_name:
		frappe.db.set_value(
			"User Permission",
			permission_name,
			{
				"is_default": 1,
				"apply_to_all_doctypes": 1,
				MANAGED_PERMISSION_FIELD: 1,
			},
			update_modified=False,
		)
		return

	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": "Sales Person",
			"for_value": sales_person,
			"is_default": 1,
			"apply_to_all_doctypes": 1,
			MANAGED_PERMISSION_FIELD: 1,
		}
	).insert(ignore_permissions=True)


def delete_managed_user_permissions(sales_person, keep_user=None):
	filters = {
		"allow": "Sales Person",
		"for_value": sales_person,
		MANAGED_PERMISSION_FIELD: 1,
	}
	if keep_user:
		filters["user"] = ["!=", keep_user]

	for permission in frappe.get_all("User Permission", filters=filters, pluck="name"):
		frappe.delete_doc("User Permission", permission, ignore_permissions=True)


@frappe.whitelist()
def get_mapped_sales_person(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None

	return frappe.db.get_value(
		"Sales Person",
		{
			MAPPED_USER_FIELD: user,
			"enabled": 1,
		},
		"name",
	)


def set_mapped_sales_person(doc, method=None):
	if not should_set_sales_person(doc):
		return

	sales_person = get_mapped_sales_person()
	if sales_person:
		doc.set("sales_person", sales_person)


def should_set_sales_person(doc):
	if not doc or doc.docstatus:
		return False
	if frappe.flags.in_install or frappe.flags.in_patch:
		return False
	if doc.doctype in {"Sales Person", "User Permission", "Custom Field"}:
		return False
	if doc.get("sales_person"):
		return False

	return frappe.get_meta(doc.doctype).has_field("sales_person")
