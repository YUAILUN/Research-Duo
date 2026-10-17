"""Local typed judgments. No provider SDK, credentials, model calls or network."""
import json
import math
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, low=0, high=1):
    require(type(value) in (int, float) and math.isfinite(value), f"{name}: finite number required")
    require(low <= value <= high, f"{name}: outside [{low}, {high}]")
    return value


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), f"{name}: nonempty string required")
    return value


def strings(value, name, nonempty=False):
    require(isinstance(value, list), f"{name}: array required")
    for item in value:
        text(item, name)
    require(len(set(value)) == len(value), f"{name}: duplicate item")
    require(bool(value) or not nonempty, f"{name}: nonempty array required")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_constant)


def load_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "input exceeds local 2 MiB limit")
    return decode(raw)


def valid_value(judgment, value):
    kind, criteria = judgment["kind"], judgment["criteria"]
    if kind == "predicate":
        return type(value) is bool
    if kind == "ordinal":
        return type(value) is int and 0 <= value < len(criteria)
    return isinstance(value, str) and value in criteria


def validate_judgment(judgment, evidence_ids):
    require(isinstance(judgment, dict), "judgment must be an object")
    fields = {"id", "kind", "question", "criteria", "value", "status", "basis", "evidence_ids", "rationale"}
    require(set(judgment) == fields, "judgment fields must match the documented contract")
    for key in ("id", "question", "rationale"):
        text(judgment[key], key)
    kind, criteria = judgment["kind"], judgment["criteria"]
    require(kind in ("choice", "ordinal", "predicate"), "invalid judgment kind")
    if kind == "predicate":
        require(isinstance(criteria, dict) and set(criteria) == {"true", "false"}, "predicate needs true/false criteria")
        for label in criteria.values():
            text(label, "predicate criterion")
    else:
        strings(criteria, "criteria", nonempty=True)
        require(len(criteria) >= 2, "at least two choices or ordered levels required")
    value, status, basis = judgment["value"], judgment["status"], judgment["basis"]
    require(status in ("grounded", "provisional", "unknown", "conflicted"), "invalid epistemic status")
    require(basis in ("observed", "inferred", "assumed"), "invalid basis")
    refs = strings(judgment["evidence_ids"], "judgment evidence_ids")
    require(set(refs) <= set(evidence_ids), "unknown evidence reference")
    if status == "unknown":
        require(value is None, "unknown judgment must use null, not false or a midpoint")
    elif status != "conflicted":
        require(value is not None, "answered judgment requires a value")
    if value is not None:
        require(valid_value(judgment, value), "value outside judgment type or criteria")
    if status == "grounded":
        require(refs and basis != "assumed", "grounded judgment needs evidence and cannot be assumed")
    return judgment
