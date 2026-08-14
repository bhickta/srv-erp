import frappe

from srv_erp.masters.dynamic_item.configuration import APPROVED, PENDING


def get_request_artifact_history(template: str, attribute: str, value: str) -> frappe._dict:
	rows = frappe.db.sql(
		"""
		select
			max(attribute_row.attribute_was_created) as attribute_created,
			max(
				case when request.status = %(approved)s then 1 else 0 end
			) as attribute_adopted,
			max(
				case when request.template_item = %(template)s
					then attribute_row.template_link_was_created else 0 end
			) as template_link_created,
			max(
				case when request.template_item = %(template)s
					and request.status = %(approved)s then 1 else 0 end
			) as template_adopted,
			max(
				case when request.template_item = %(template)s
					then attribute_row.profile_row_was_created else 0 end
			) as profile_row_created,
			max(
				case when attribute_row.attribute_value = %(value)s
					then attribute_row.value_was_created else 0 end
			) as value_created,
			max(
				case when attribute_row.attribute_value = %(value)s
					and request.status = %(approved)s then 1 else 0 end
			) as value_adopted,
			max(
				case when attribute_row.attribute_value = %(value)s
					then attribute_row.master_was_created else 0 end
			) as master_created
		from `tabDynamic Item Request Attribute` attribute_row
		inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
		where attribute_row.item_attribute = %(attribute)s
		""",
		{
			"approved": APPROVED,
			"template": template,
			"attribute": attribute,
			"value": value,
		},
		as_dict=True,
	)
	return frappe._dict(rows[0] if rows else {})


def attribute_used_by_template_variant(template: str, attribute: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabItem Variant Attribute` attribute_row
			inner join `tabItem` item on item.name = attribute_row.parent
			where item.variant_of = %(template)s
				and attribute_row.attribute = %(attribute)s
			limit 1
			""",
			{"template": template, "attribute": attribute},
		)
	)


def attribute_used_by_other_request(request_name: str, template: str, attribute: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabDynamic Item Request Attribute` attribute_row
			inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
			where request.name != %(request_name)s
				and request.template_item = %(template)s
				and request.status = %(pending)s
				and attribute_row.item_attribute = %(attribute)s
			limit 1
			""",
			{
				"request_name": request_name,
				"template": template,
				"pending": PENDING,
				"attribute": attribute,
			},
		)
	)


def attribute_value_is_referenced(request_name: str, attribute: str, value: str) -> bool:
	if frappe.db.exists(
		"Item Variant Attribute",
		{"attribute": attribute, "attribute_value": value},
	):
		return True
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabDynamic Item Request Attribute` attribute_row
			inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
			where request.name != %(request_name)s
				and request.status = %(pending)s
				and attribute_row.item_attribute = %(attribute)s
				and attribute_row.attribute_value = %(value)s
			limit 1
			""",
			{
				"request_name": request_name,
				"pending": PENDING,
				"attribute": attribute,
				"value": value,
			},
		)
	)


def brand_is_referenced(brand: str) -> bool:
	if frappe.db.exists("Item", {"brand": brand}):
		return True
	return frappe.db.exists(
		"Item Variant Attribute",
		{"attribute": "Brand", "attribute_value": brand},
	)
