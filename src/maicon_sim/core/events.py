import hashlib
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def event_hash(events):
    return hashlib.sha256(('\n'.join(canonical(e) for e in events)).encode()).hexdigest()
