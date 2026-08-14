from srv_erp.masters.doctype.dynamic_item_request.dynamic_item_request import (
	on_doctype_update as update_request_indexes,
)
from srv_erp.masters.doctype.dynamic_item_request_attribute.dynamic_item_request_attribute import (
	on_doctype_update as update_attribute_indexes,
)
from srv_erp.masters.doctype.dynamic_item_request_uom.dynamic_item_request_uom import (
	on_doctype_update as update_uom_indexes,
)


def execute():
	update_request_indexes()
	update_attribute_indexes()
	update_uom_indexes()
