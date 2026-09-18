"""common.py — paths, loaders and the tiny JSON-Schema checker shared by every tool.

Stdlib only, Python 3.9+. Every external location is overridable by an
environment variable so the project keeps working when a sibling repo moves.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
KINDS = DATA / "kinds"
IMAGES = DATA / "images"
VOCAB = DATA / "vocab"
SOURCES = DATA / "sources" / "sources.json"
SCHEMA = ROOT / "schema" / "kind.schema.json"
BUILD = ROOT / "build"
VENDOR = ROOT / "vendor"

PROJECTS = Path(os.environ.get("NAN_PROJECTS") or (Path.home() / "Developer" / "claude code projects"))
VAULT_VOCAB = Path(os.environ.get("VAULT_VOCAB") or (PROJECTS / "wichaa-vault" / "_meta" / "vocab"))
CATALOG_DB = Path(os.environ.get("CATALOG_DB") or (PROJECTS / "manuscript-crawler" / "crawler" / "catalog.db"))
SEARCH_CORE = Path(os.environ.get("SEARCH_CORE") or (PROJECTS / "search-core"))
CRAWLER = Path(os.environ.get("CRAWLER_DIR") or (PROJECTS / "manuscript-crawler"))
WATS_JSON = Path(os.environ.get("WATS_JSON") or (PROJECTS / "manuscript-wiki" / "data" / "wats-detail.json"))

TIERS = ("catalogue", "cited", "tradition", "inference", "field")
TIER_LABEL_EN = {
    "catalogue": "Catalogue — checkable against the corpus (catalog.db, a transcribed treatise)",
    "cited": "Cited — a named external source, linked",
    "tradition": "Tradition — general knowledge of the wider tradition, hedged",
    "inference": "Inference — this project's own reasoning from the above",
    "field": "Field — someone stood there",
}
TIER_LABEL_TH = {
    "catalogue": "จากคลัง",
    "cited": "อ้างอิงแหล่ง",
    "tradition": "ตามประเพณี",
    "inference": "อนุมาน",
    "field": "พบเห็นเอง",
}


def jload(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jdump(obj, path: Path, indent=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def load_kinds() -> list[dict]:
    """Every record under data/kinds, sorted by id. Skips files that are not JSON objects."""
    out = []
    for p in sorted(KINDS.glob("*.json")):
        d = jload(p)
        if isinstance(d, dict):
            d["_path"] = str(p)
            out.append(d)
    return out


def load_sources() -> dict:
    if not SOURCES.exists():
        return {}
    return {s["id"]: s for s in jload(SOURCES)["sources"]}


def load_vocab(name: str) -> dict:
    """data/vocab/<name>.json → {key: entry}. Empty dict if the snapshot is missing."""
    p = VOCAB / f"{name}.json"
    if not p.exists():
        return {}
    d = jload(p)
    return {e["key"]: e for e in d.get("entries", [])}


def load_wats() -> dict:
    return jload(WATS_JSON) if WATS_JSON.exists() else {}


def search_core():
    """Import the fleet search core: the live copy in search-core/ first, the vendored copy as fallback."""
    for d in (SEARCH_CORE, VENDOR):
        if (d / "searchcore.py").exists():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            import searchcore  # noqa: E402
            return searchcore, d
    raise RuntimeError("searchcore.py not found in search-core/ or vendor/")


# ------------------------------------------------------------ mini JSON Schema
# Enough of draft 2020-12 to enforce kind.schema.json: type, const, enum,
# required, properties, additionalProperties, patternProperties, items,
# minItems/maxItems, minLength, pattern, $ref (local only). Returns a list of
# "path: problem" strings. No dependency, so validation runs anywhere.

_TYPES = {
    "object": dict, "array": list, "string": str, "integer": int,
    "number": (int, float), "boolean": bool, "null": type(None),
}


def _resolve(ref: str, root: dict):
    assert ref.startswith("#/"), ref
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def check(value, schema: dict, root: dict, path="$") -> list[str]:
    errs: list[str] = []
    if "$ref" in schema:
        return check(value, _resolve(schema["$ref"], root), root, path)
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = False
        for tt in types:
            py = _TYPES[tt]
            if tt == "integer" and isinstance(value, bool):
                continue
            if tt == "number" and isinstance(value, bool):
                continue
            if isinstance(value, py):
                ok = True
                break
        if not ok:
            return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(value):
                errs += check(v, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in value:
                errs.append(f"{path}: missing required '{r}'")
        pats = schema.get("patternProperties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                errs += check(v, props[k], root, f"{path}.{k}")
                continue
            matched = False
            for pat, sub in pats.items():
                if re.search(pat, k):
                    matched = True
                    if sub:
                        errs += check(v, sub, root, f"{path}.{k}")
            if matched:
                continue
            if addl is False:
                errs.append(f"{path}: unexpected key '{k}'")
            elif isinstance(addl, dict):
                errs += check(v, addl, root, f"{path}.{k}")
    return errs


def validate_record(rec: dict, schema: dict | None = None) -> list[str]:
    schema = schema or jload(SCHEMA)
    clean = {k: v for k, v in rec.items() if not k.startswith("_")}
    return check(clean, schema, schema)
