#!/usr/bin/env python3
"""Fixed dispatch and evidence-based acceptance for Partner identity tryouts."""

from __future__ import annotations

import json


EXPECTED_FAST = {"a": [2, 1], "b": {"a": {"c": 3}, "z": 1}, "c": "x"}


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str):
    raise ValueError("non-finite JSON number")


def keys_are_sorted(value) -> bool:
    if isinstance(value, dict):
        return list(value) == sorted(value) and all(keys_are_sorted(v) for v in value.values())
    if isinstance(value, list):
        return all(keys_are_sorted(v) for v in value)
    return True


def validate_fast_worker(text: str) -> dict:
    result = {"passed": False, "format_valid": False, "content_valid": False,
              "keys_sorted": False, "errors": []}
    lines = text.strip().splitlines()
    fenced = len(lines) >= 3 and lines[0] in ("```", "```json") and lines[-1] == "```"
    if fenced:
        result["errors"].append("markdown_fence")
        text = "\n".join(lines[1:-1])
    try:
        value = json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, RecursionError) as error:
        result["errors"].append("invalid_json: " + str(error))
        return result
    result["format_valid"] = not fenced
    # Dict equality alone treats true as 1; preserve JSON value types as well.
    result["content_valid"] = json.dumps(value, sort_keys=True) == json.dumps(EXPECTED_FAST, sort_keys=True)
    result["keys_sorted"] = keys_are_sorted(value)
    if not result["content_valid"]:
        result["errors"].append("content_mismatch")
    if not result["keys_sorted"]:
        result["errors"].append("keys_not_sorted")
    result["passed"] = all(result[key] for key in ("format_valid", "content_valid", "keys_sorted"))
    return result
