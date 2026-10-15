"""Input locations and structural comparison helpers."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def load_json(name, root=ROOT):
    return json.loads((Path(root) / name).read_text(encoding="utf-8"))


def record_key(value):
    """Typed immutable key for equality grouping, not a ranking/selection key."""
    if isinstance(value, dict):
        return ("object", tuple((key, record_key(item)) for key, item in sorted(value.items())))
    if isinstance(value, (list, tuple)):
        return ("array", tuple(record_key(item) for item in value))
    return (type(value).__name__, value)


def json_value(value):
    """Convert Python tuples to the array representation stored in JSON."""
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value
