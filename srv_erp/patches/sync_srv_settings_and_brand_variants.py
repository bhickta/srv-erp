from srv_erp.variant_auto_creation import set_srv_settings_defaults, sync_missing_brand_variants


def execute():
	set_srv_settings_defaults()
	sync_missing_brand_variants(enqueue=False)
