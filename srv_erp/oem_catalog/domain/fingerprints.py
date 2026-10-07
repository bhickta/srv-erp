from decimal import Decimal
import hashlib
import json

PROTECTED_ITEM_FIELDS = ('stock_uom', 'brand', 'has_variants', 'variant_of', 'is_stock_item',
                         'disabled', 'package_barcode_qty_entry_rule')


def fingerprint(item):
    payload = {key: item.get(key) for key in PROTECTED_ITEM_FIELDS}
    payload['attributes'] = sorted((row.get('attribute'), row.get('attribute_value')) for row in item.get('attributes', []))
    payload['uoms'] = sorted((row.get('uom'), format(Decimal(str(row.get('conversion_factor'))).normalize(), 'f')) for row in item.get('uoms', []))
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()
