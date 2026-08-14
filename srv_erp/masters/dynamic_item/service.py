"""Compatibility facade for the dynamic Item domain services.

New code should import from the focused modules directly. Existing integrations may
continue importing these symbols from ``service`` without a breaking change.
"""

from srv_erp.masters.dynamic_item.approval_flow import (
	approve_request,
	cancel_request,
	get_request_status,
	reject_request,
	terminate_request,
)
from srv_erp.masters.dynamic_item.artifact_usage import (
	attribute_used_by_other_request,
	attribute_used_by_template_variant,
	attribute_value_is_referenced,
	brand_is_referenced,
	get_request_artifact_history,
)
from srv_erp.masters.dynamic_item.assignments import (
	assign_request_to_approvers,
	close_approval_assignments,
	require_available_approver,
)
from srv_erp.masters.dynamic_item.cleanup import (
	cleanup_attribute_artifacts,
	cleanup_request_schema,
	delete_staged_item,
)
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context
from srv_erp.masters.dynamic_item.exceptions import DynamicItemConflict
from srv_erp.masters.dynamic_item.item_approval import (
	approve_packaging_request,
	approve_staged_variant,
	get_request_attributes,
)
from srv_erp.masters.dynamic_item.lookups import (
	canonicalize_known_masters,
	get_case_insensitive_attribute_value,
	get_case_insensitive_name,
)
from srv_erp.masters.dynamic_item.normalization import (
	MAX_ATTRIBUTES,
	MAX_PACKAGING_UOMS,
	normalize_attributes,
	normalize_text,
	normalize_uoms,
	parse_payload,
)
from srv_erp.masters.dynamic_item.packaging import (
	add_packaging_rows,
	get_missing_packaging,
	validate_no_overlapping_packaging_request,
)
from srv_erp.masters.dynamic_item.profile import (
	get_profile_rules,
	get_template_and_profile,
	validate_numeric_value,
	validate_requested_attributes,
	validate_source,
)
from srv_erp.masters.dynamic_item.repository import (
	get_item_state,
	get_pending_request,
	get_variant_if_present,
	insert_request,
	lock_request,
	lock_template,
)
from srv_erp.masters.dynamic_item.request_flow import (
	create_packaging_request,
	create_variant_request,
	resolve_or_request,
	validate_existing_variant,
)
from srv_erp.masters.dynamic_item.results import (
	approved_result,
	existing_result,
	request_result,
	terminal_result,
)
from srv_erp.masters.dynamic_item.signatures import (
	make_identity_signature,
	make_packaging_signature,
)
from srv_erp.masters.dynamic_item.staging import (
	ensure_attribute_value,
	ensure_item_attribute,
	stage_requested_schema,
	stage_variant_item,
)

__all__ = [
	"MAX_ATTRIBUTES",
	"MAX_PACKAGING_UOMS",
	"DynamicItemConflict",
	"add_packaging_rows",
	"approve_packaging_request",
	"approve_request",
	"approve_staged_variant",
	"approved_result",
	"assign_request_to_approvers",
	"attribute_used_by_other_request",
	"attribute_used_by_template_variant",
	"attribute_value_is_referenced",
	"brand_is_referenced",
	"cancel_request",
	"canonicalize_known_masters",
	"cleanup_attribute_artifacts",
	"cleanup_request_schema",
	"close_approval_assignments",
	"create_packaging_request",
	"create_variant_request",
	"delete_staged_item",
	"dynamic_item_service_context",
	"ensure_attribute_value",
	"ensure_item_attribute",
	"existing_result",
	"get_case_insensitive_attribute_value",
	"get_case_insensitive_name",
	"get_item_state",
	"get_missing_packaging",
	"get_pending_request",
	"get_profile_rules",
	"get_request_artifact_history",
	"get_request_attributes",
	"get_request_status",
	"get_template_and_profile",
	"get_variant_if_present",
	"insert_request",
	"lock_request",
	"lock_template",
	"make_identity_signature",
	"make_packaging_signature",
	"normalize_attributes",
	"normalize_text",
	"normalize_uoms",
	"parse_payload",
	"reject_request",
	"request_result",
	"require_available_approver",
	"resolve_or_request",
	"stage_requested_schema",
	"stage_variant_item",
	"terminal_result",
	"terminate_request",
	"validate_existing_variant",
	"validate_no_overlapping_packaging_request",
	"validate_numeric_value",
	"validate_requested_attributes",
	"validate_source",
]
