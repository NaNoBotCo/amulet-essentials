#!/usr/bin/env python3
"""validate.py — every record must pass before anything is built or published.

Checks, in order:
  1. schema/kind.schema.json (structure, enums, patterns)
  2. id == filename; parent exists; confusable_with targets exist
  3. axes keys exist in the vault snapshot (class / functions / materials)
  4. region keys — WARN only (the list is open by design)
  5. every source id exists in data/sources/sources.json
  6. every image licence is on the free-to-use allowlist and its file exists
  7. provenance.fields paths point at real fields

Exit 1 on any error. Warnings never fail the build; they are printed so they
are seen.

    python3 tools/validate.py            # all records
    python3 tools/validate.py --strict   # warnings fail too
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, KINDS, SCHEMA, jload, load_kinds, load_sources, load_vocab, validate_record  # noqa: E402

FREE_LICENSES = re.compile(
    r"^(CC0(\s*1\.0)?|Public domain|PD(-[A-Za-z0-9-]+)?|CC[- ]BY(-SA)?(\s*[1-4]\.[0-9])?|FAL(\s*1\.[0-9])?)$", re.I)


def _get(rec: dict, dotted: str):
    node = rec
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def validate_all(strict=False) -> int:
    schema = jload(SCHEMA)
    recs = load_kinds()
    ids = {r["id"] for r in recs}
    sources = load_sources()
    classes = load_vocab("classes")
    materials = load_vocab("materials")
    functions = load_vocab("functions")
    regions = {e["key"] for e in jload(KINDS.parent / "vocab" / "regions.json")["entries"]}
    errors: list[str] = []
    warns: list[str] = []
    for r in recs:
        tag = r["id"]
        for e in validate_record(r, schema):
            errors.append(f"{tag}: {e}")
        if Path(r["_path"]).stem != r["id"]:
            errors.append(f"{tag}: filename {Path(r['_path']).name} != id")
        if r.get("parent") and r["parent"] not in ids:
            errors.append(f"{tag}: parent {r['parent']} not found")
        for c in r.get("confusable_with", []):
            if c["id"] not in ids:
                errors.append(f"{tag}: confusable_with {c['id']} not found")
        ax = r.get("axes", {})
        if classes and ax.get("class") and ax["class"] not in classes:
            errors.append(f"{tag}: class {ax['class']} not in vault snapshot")
        for f in ax.get("functions", []):
            if functions and f not in functions:
                errors.append(f"{tag}: function {f} not in vault snapshot")
        for m in ax.get("materials", []):
            if materials and m not in materials:
                errors.append(f"{tag}: material {m} not in vault snapshot")
        for reg in r.get("region", []):
            if reg not in regions:
                warns.append(f"{tag}: region {reg} not in regions.json (open list — add it there)")
        for s in r.get("sources", []):
            if s not in sources:
                errors.append(f"{tag}: source {s} not in sources.json")
        for d in r.get("diagnostics", []):
            if d.get("source") and d["source"] not in sources:
                errors.append(f"{tag}: diagnostic source {d['source']} not in sources.json")
        for i, im in enumerate(r.get("images", [])):
            if not FREE_LICENSES.match(im["license"].strip()):
                errors.append(f"{tag}: images[{i}] licence {im['license']!r} is not on the free-to-use allowlist")
            if not (IMAGES / im["file"]).exists():
                warns.append(f"{tag}: images[{i}] file missing: {im['file']}")
        for path in r.get("provenance", {}).get("fields", {}):
            if _get(r, path) is None:
                warns.append(f"{tag}: provenance.fields.{path} names a field the record does not have")
        if not r.get("text", {}).get("what_th"):
            warns.append(f"{tag}: no what_th (Thai description)")
        if not r.get("images"):
            warns.append(f"{tag}: no images yet")
    for w in warns:
        print("warn ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(recs)} records · {len(errors)} errors · {len(warns)} warnings")
    if errors or (strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    sys.exit(validate_all(ap.parse_args().strict))
