def generate(item_code, uom, count):
    from srv_erp.package_barcode.service import PackageBarcodeGenerator
    return dict(PackageBarcodeGenerator(item_code=item_code, uom=uom, no_of_barcodes=count).generate())
