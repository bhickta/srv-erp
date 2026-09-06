import json

import frappe
from frappe import _
from frappe.model import NO_VALUE_FIELDS
from frappe.utils import cint

MANAGER_ROLE_FIELD = "grid_column_manager_role"
TEMPLATES_FIELD = "grid_column_templates"


def add_grid_column_templates_to_boot(bootinfo):
	"""Expose shared grid layouts before forms synchronously build their grids."""
	manager_role = frappe.db.get_single_value("SRV Settings", MANAGER_ROLE_FIELD)
	bootinfo.srv_erp_grid_columns = {
		"can_publish": bool(manager_role and manager_role in frappe.get_roles()),
		"templates": get_grid_column_templates(),
	}


def get_grid_column_templates():
	raw_templates = frappe.db.get_single_value("SRV Settings", TEMPLATES_FIELD)
	if not raw_templates:
		return {}

	try:
		templates = json.loads(raw_templates)
	except (TypeError, ValueError):
		return {}

	return templates if isinstance(templates, dict) else {}


@frappe.whitelist()
def publish_grid_columns(parent_doctype, child_doctype, columns):
	"""Publish the current user's selected child-grid columns as a shared layout."""
	_validate_publisher()
	validated_columns = _validate_grid_columns(parent_doctype, child_doctype, columns)

	templates = get_grid_column_templates()
	templates.setdefault(parent_doctype, {})[child_doctype] = validated_columns
	frappe.db.set_single_value(
		"SRV Settings", TEMPLATES_FIELD, json.dumps(templates, separators=(",", ":"), sort_keys=True)
	)
	clear_grid_column_template_boot_cache()

	return {
		"parent_doctype": parent_doctype,
		"child_doctype": child_doctype,
		"columns": validated_columns,
	}


def clear_grid_column_template_boot_cache():
	frappe.cache.delete_key("bootinfo")


def _validate_publisher():
	manager_role = frappe.db.get_single_value("SRV Settings", MANAGER_ROLE_FIELD)
	if not manager_role or manager_role not in frappe.get_roles():
		frappe.throw(
			_("You need the role configured in SRV Settings to publish grid columns."),
			frappe.PermissionError,
		)


def _validate_grid_columns(parent_doctype, child_doctype, columns):
	parent_meta = frappe.get_meta(parent_doctype)
	if not any(df.options == child_doctype for df in parent_meta.get_table_fields()):
		frappe.throw(_("{0} is not a child table of {1}.").format(child_doctype, parent_doctype))

	columns = frappe.parse_json(columns)
	if not isinstance(columns, list) or not columns:
		frappe.throw(_("Select at least one grid column."))

	child_meta = frappe.get_meta(child_doctype)
	validated_columns = []
	seen_fields = set()
	total_width = 0
	for column in columns:
		if not isinstance(column, dict):
			frappe.throw(_("Invalid grid column configuration."))

		fieldname = column.get("fieldname")
		field = child_meta.get_field(fieldname)
		if (
			not field
			or fieldname in seen_fields
			or field.hidden
			or (field.fieldtype in NO_VALUE_FIELDS and field.fieldtype != "Button")
		):
			frappe.throw(_("Invalid grid column: {0}").format(fieldname or ""))

		width = cint(column.get("columns"))
		if width < 1 or width > 10:
			frappe.throw(_("Grid column widths must be between 1 and 10."))

		seen_fields.add(fieldname)
		total_width += width
		validated_columns.append({"fieldname": fieldname, "columns": width})

	if total_width > 10:
		frappe.throw(_("The total grid column width cannot be more than 10."))

	return validated_columns
