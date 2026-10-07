from decimal import Decimal

from .models import CatalogError

OPS = {'eq', 'ne', 'in', 'not_in', 'exists', 'gt', 'gte', 'lt', 'lte'}


def validate_condition(node, attributes, depth=0, budget=None):
    budget = [0] if budget is None else budget
    budget[0] += 1
    if depth > 4 or budget[0] > 200 or not isinstance(node, dict):
        raise CatalogError('INVALID_INPUT', 'Rule nesting or operation limit exceeded')
    groups = set(node) & {'all', 'any', 'not'}
    if groups:
        if len(groups) != 1 or len(node) != 1:
            raise CatalogError('INVALID_INPUT', 'Invalid boolean condition')
        group = next(iter(groups))
        children = [node[group]] if group == 'not' else node[group]
        if not isinstance(children, list) or not children:
            raise CatalogError('INVALID_INPUT', 'Empty boolean condition')
        for child in children:
            validate_condition(child, attributes, depth + 1, budget)
        return
    if set(node) - {'field', 'op', 'value'} or node.get('field') not in attributes or node.get('op') not in OPS:
        raise CatalogError('INVALID_INPUT', 'Unknown rule field or operator')
    op, value = node['op'], node.get('value')
    if op != 'exists' and 'value' not in node:
        raise CatalogError('INVALID_INPUT', 'Rule comparison value is required')
    if op in {'in', 'not_in'} and (not isinstance(value, list) or len(value) > 500):
        raise CatalogError('INVALID_INPUT', 'Rule membership requires a bounded list')
    if op in {'gt', 'gte', 'lt', 'lte'} and attributes[node['field']].kind != 'Decimal':
        raise CatalogError('INVALID_INPUT', 'Ordering is only allowed on decimal attributes')
    from .canonicalization import typed_value
    if op != 'exists':
        for item in value if op in {'in', 'not_in'} else [value]:
            typed_value(attributes[node['field']], item)


def matches(node, values):
    if 'all' in node:
        return all(matches(child, values) for child in node['all'])
    if 'any' in node:
        return any(matches(child, values) for child in node['any'])
    if 'not' in node:
        return not matches(node['not'], values)
    field, op = node['field'], node['op']
    if op == 'exists':
        return field in values and values[field] is not None and values[field] != ''
    if field not in values:
        return False
    left, right = values[field], node['value']
    if op in {'gt', 'gte', 'lt', 'lte'}:
        left, right = Decimal(str(left)), Decimal(str(right))
    return {'eq': lambda: left == right, 'ne': lambda: left != right,
            'in': lambda: left in right, 'not_in': lambda: left not in right,
            'gt': lambda: left > right, 'gte': lambda: left >= right,
            'lt': lambda: left < right, 'lte': lambda: left <= right}[op]()


def validate_rules(rules, attributes):
    if len(rules) > 200:
        raise CatalogError('INVALID_INPUT', 'Too many rules')
    mapping = {a.key: a for a in attributes}
    budget = [0]
    for rule in rules:
        if set(rule) - {'when', 'require', 'allowed', 'message'} or 'when' not in rule:
            raise CatalogError('INVALID_INPUT', 'Invalid rule structure')
        validate_condition(rule['when'], mapping, budget=budget)
        if set(rule.get('require', [])) - set(mapping):
            raise CatalogError('INVALID_INPUT', 'Unknown required key')
        for key, choices in rule.get('allowed', {}).items():
            if key not in mapping or not isinstance(choices, list) or len(choices) > 500:
                raise CatalogError('INVALID_INPUT', 'Invalid allowed values')
            from .canonicalization import typed_value
            for choice in choices:
                typed_value(mapping[key], choice)


def apply_rules(rules, values, attributes):
    validate_rules(rules, attributes)
    allowed, required = {}, set()
    for rule in rules:
        if matches(rule['when'], values):
            required.update(rule.get('require', []))
            for key, choices in rule.get('allowed', {}).items():
                allowed[key] = set(choices) & allowed.get(key, set(choices))
                if not allowed[key]:
                    raise CatalogError('CONFIGURATION_CONFLICT', 'Applicable constraints allow no values', key)
    for key in required:
        if key not in values or values[key] is None or values[key] == '':
            raise CatalogError('MISSING_PHYSICAL_VALUE', 'A conditional value is required', key)
    for key, choices in allowed.items():
        if key in values and values[key] not in choices:
            raise CatalogError('CONFIGURATION_CONFLICT', 'Value violates an applicable constraint', key)
    return allowed, required
