from srv_erp.masters.dynamic_item.configuration import ADD_PACKAGING, APPROVED


def request_result(request, created: bool = False) -> dict:
	return {
		"outcome": "packaging_approval_required"
		if request.request_type == ADD_PACKAGING
		else "pending_approval",
		"item_code": request.staged_item_code or request.resolved_item,
		"request": request.name,
		"approval_status": request.status,
		"created": bool(created),
	}


def existing_result(item_code: str) -> dict:
	return {
		"outcome": "existing",
		"item_code": item_code,
		"request": None,
		"approval_status": APPROVED,
		"created": False,
	}


def approved_result(request) -> dict:
	return {
		"outcome": "approved",
		"request": request.name,
		"item_code": request.resolved_item,
		"approval_status": request.status,
	}


def terminal_result(request) -> dict:
	return {
		"outcome": request.status.lower().replace(" ", "_"),
		"request": request.name,
		"item_code": request.resolved_item,
		"approval_status": request.status,
	}
