#!/usr/bin/env python3
"""Inline all local $ref (#/$defs/Name) in a JSON Schema and drop $defs.

json-schema-to-zod does not resolve Draft 2020-12 $defs references (it leaves them
as z.any(), making zod validation shallow and inconsistent with the deeply-validated
pydantic models). Our $defs are local and non-circular, so we fully inline them before
feeding the schema to the zod generator. Usage: _deref.py <in.json> <out.json>
"""
import copy
import json
import sys


def deref(node, defs):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.split("/")[-1]
            return deref(copy.deepcopy(defs[name]), defs)
        return {k: deref(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [deref(v, defs) for v in node]
    return node


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as fh:
        schema = json.load(fh)
    defs = schema.get("$defs", {})
    inlined = deref(schema, defs)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(inlined, fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
