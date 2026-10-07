import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from .models import Attribute, CatalogError, Identity, Schema

KEY = re.compile(r'^[a-z][a-z0-9_]{0,63}$', re.ASCII)


def fail(message, field=None):
    raise CatalogError('INVALID_INPUT', message, field)


def decimal_value(value, attribute: Attribute):
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        fail('Use an exact decimal string', attribute.key)
    try:
        number = Decimal(value)
    except InvalidOperation:
        fail('Invalid decimal', attribute.key)
    if not number.is_finite() or len(number.as_tuple().digits) > 30 or abs(number.adjusted()) > 30:
        fail('Decimal is not finite or exceeds bounds', attribute.key)
    quantum = Decimal(1).scaleb(-attribute.precision)
    if number != number.quantize(quantum):
        fail('Excessive decimal precision', attribute.key)
    if attribute.minimum is not None and number < Decimal(attribute.minimum):
        fail('Value is below minimum', attribute.key)
    if attribute.maximum is not None and number > Decimal(attribute.maximum):
        fail('Value is above maximum', attribute.key)
    if attribute.step:
        step = Decimal(attribute.step)
        if step <= 0 or (number - Decimal(attribute.minimum or '0')) % step:
            fail('Value does not follow the published step', attribute.key)
    return '0' if number == 0 else format(number.normalize(), 'f')


def typed_value(attribute, value):
    if attribute.multiple:
        if not isinstance(value, list) or len(value) > 500:
            fail('Expected a bounded list', attribute.key)
        from dataclasses import replace
        values = [typed_value(replace(attribute, multiple=False), item) for item in value]
        return values if attribute.ordered else sorted(set(values))
    if attribute.kind == 'Decimal':
        return decimal_value(value, attribute)
    if attribute.kind == 'Boolean':
        if not isinstance(value, bool):
            fail('Expected a boolean', attribute.key)
        return value
    if not isinstance(value, str):
        fail('Expected a string', attribute.key)
    value = unicodedata.normalize('NFC', value).strip()
    if not value or len(value) > attribute.max_length or any(ord(c) < 32 for c in value):
        fail('Text is blank, too long, or contains control characters', attribute.key)
    if attribute.kind in ('Enum', 'AssetRevision', 'MasterLink'):
        if value not in attribute.choices:
            fail('Choose an approved stable value', attribute.key)
    elif attribute.kind != 'Text':
        fail('Unknown attribute type', attribute.key)
    return value


def canonicalize(schema: Schema, supplied: dict) -> Identity:
    if not isinstance(supplied, dict) or len(supplied) > 64:
        fail('Expected at most 64 attribute values')
    keys = [a.key for a in schema.attributes]
    if len(keys) != len(set(keys)) or any(not KEY.fullmatch(k) for k in keys):
        fail('Invalid or duplicate schema keys')
    if set(supplied) - set(keys):
        fail('Unknown attribute values')
    if not schema.product or not schema.namespace or not schema.stock_uom:
        fail('Missing Product, namespace, or stock UOM')
    identity, all_values = {}, {}
    for attribute in schema.attributes:
        value = supplied.get(attribute.key)
        if value is None or value == '' or value == []:
            if attribute.required or attribute.identity:
                raise CatalogError('MISSING_PHYSICAL_VALUE', 'Choose a value or explicit not-applicable option', attribute.key)
            continue
        normalized = typed_value(attribute, value)
        all_values[attribute.key] = normalized
        if attribute.identity:
            identity[attribute.key] = normalized
    payload = {'identity_namespace': schema.namespace, 'product': schema.product,
               'stock_uom': schema.stock_uom, 'attributes': identity}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return Identity(encoded, hashlib.sha256(encoded.encode('utf-8')).hexdigest(), all_values)


def compare_identity(left: Identity, right: Identity):
    if left.digest == right.digest and left.canonical_json != right.canonical_json:
        raise CatalogError('CONFIGURATION_CONFLICT', 'Identity hash collision')
    return left.canonical_json == right.canonical_json
