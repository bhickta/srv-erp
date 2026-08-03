from srv_erp.install import create_brand_custom_fields
from srv_erp.item.variant_auto_creation import sync_attribute_brand_values_to_master


def execute():
	create_brand_custom_fields()
	sync_attribute_brand_values_to_master()
