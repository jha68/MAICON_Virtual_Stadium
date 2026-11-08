"""Strict public report normalization for the 2026-11-04 SIM profile."""
import math
from .types import SECTORS, FACILITIES, BASES, SLOTS, OBJECT_CLASSES, camp_for_slot


class EngineError(Exception):
    def __init__(self, status, detail):
        self.status = status
        self.status_code = status
        self.detail = detail
        super().__init__(str(detail))


def invalid(message, loc=()):
    raise EngineError(422, [{'loc': ['body', *loc], 'msg': message, 'type': 'value_error'}])


def keys(value, allowed, required=()):
    if not isinstance(value, dict):
        invalid('must be an object')
    if set(value) - set(allowed):
        invalid('unknown field', (sorted(set(value) - set(allowed))[0],))
    for key in required:
        if key not in value:
            invalid('field required', (key,))


def enum(value, allowed, loc=()):
    if not isinstance(value, str) or value.upper() not in allowed:
        invalid('invalid enum value', loc)
    return value.upper()


def finite_number(value, low, high, loc=()):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        invalid(f'must be a finite number between {low} and {high}', loc)
    return value


def normalize_m1(payload):
    keys(payload, ('mission_code', 'target', 'search_sectors', 'base'))
    value = {k: None for k in ('target', 'search_sectors', 'base')}
    for key, allowed in (('target', FACILITIES), ('base', BASES)):
        if payload.get(key) is not None:
            value[key] = enum(payload[key], allowed, (key,))
    if payload.get('search_sectors') is not None:
        raw = payload['search_sectors']
        if not isinstance(raw, list) or len(raw) > 7:
            invalid('search_sectors must be a list with at most 7 sectors', ('search_sectors',))
        result = [enum(x, SECTORS, ('search_sectors', i)) for i, x in enumerate(raw)]
        if len(set(result)) != len(result):
            invalid('duplicate sector', ('search_sectors',))
        value['search_sectors'] = sorted(result)
    if all(x is None for x in value.values()):
        invalid('at least one non-null report field is required')
    return value


def normalize_m3(payload):
    keys(payload, ('mission_code', 'sectors'), ('sectors',))
    sectors = payload['sectors']
    if not isinstance(sectors, list) or not 1 <= len(sectors) <= 7:
        invalid('sectors must contain 1 to 7 entries', ('sectors',))
    seen = set()
    result = []
    for i, item in enumerate(sectors):
        keys(item, ('sector', 'objects'), ('sector', 'objects'))
        sector = enum(item['sector'], SECTORS, ('sectors', i, 'sector'))
        if sector in seen:
            invalid('duplicate sector', ('sectors', i, 'sector'))
        seen.add(sector)
        objects = item['objects']
        if not isinstance(objects, list) or len(objects) > 6:
            invalid('objects must contain at most 6 entries', ('sectors', i, 'objects'))
        classes, normalized = set(), []
        for j, obj in enumerate(objects):
            keys(obj, ('type', 'count'), ('type', 'count'))
            cls = enum(obj['type'], OBJECT_CLASSES, ('sectors', i, 'objects', j, 'type'))
            count = obj['count']
            if type(count) is not int or not 0 <= count <= 99:
                invalid('count must be an integer between 0 and 99', ('sectors', i, 'objects', j, 'count'))
            if cls in classes:
                invalid('duplicate type', ('sectors', i, 'objects', j, 'type'))
            classes.add(cls)
            if count:
                normalized.append({'type': cls, 'count': count})
        result.append({'sector': sector, 'objects': sorted(normalized, key=lambda x: x['type'])})
    return {'sectors': sorted(result, key=lambda x: x['sector'])}


def normalize_m6(payload, camp):
    keys(payload, ('mission_code', 'ranking'), ('ranking',))
    raw = payload['ranking']
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3:
        invalid('ranking must contain 1 to 3 opponent slots', ('ranking',))
    result = [enum(x, SLOTS, ('ranking', i)) for i, x in enumerate(raw)]
    if any(camp_for_slot(x) == camp for x in result) or len(result) != len(set(result)):
        invalid('ranking must contain unique opponent slots', ('ranking',))
    return {'ranking': result}
