#!/usr/bin/env python3
"""sync_vocab.py — snapshot the wichaa vault vocabularies into data/vocab/*.json.

The vault (wichaa-vault/_meta/vocab/{classes,materials,functions}.md) is the
asserted layer for class / material / function. This reads the vault and keeps
a JSON snapshot beside it, so validation and builds work when the vault is
absent (another machine, a moved folder, a future split).

The vault's YAML lives in ```yaml fences as a list of flat mappings with
scalars, [inline, lists] and `>` folded text. That is all the parser here
understands — deliberately: a full YAML parser is a dependency, and the vault's
shape is fixed by its own SCHEMA.md.

    python3 tools/sync_vocab.py          # refresh the snapshot
    python3 tools/sync_vocab.py --check  # exit 1 if the snapshot is stale
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import VAULT_VOCAB, VOCAB, jdump, jload  # noqa: E402

AXES = ("classes", "materials", "functions")


def _scalar(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [x.strip().strip("'\"") for x in inner.split(",")] if inner else []
    if s in ("true", "false"):
        return s == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if s == "null" or s == "~":
        return None
    return s.strip("'\"")


def parse_entries(md: str) -> list[dict]:
    """Every `- key:` mapping inside every ```yaml fence, in order."""
    entries: list[dict] = []
    for block in re.findall(r"```yaml\n(.*?)```", md, re.S):
        cur: dict | None = None
        folded_key: str | None = None
        for raw in block.split("\n"):
            line = raw.rstrip()
            if not line.strip() or line.strip().startswith("#"):
                continue
            if line.startswith("- "):
                if cur:
                    entries.append(cur)
                cur = {}
                folded_key = None
                line = "  " + line[2:]
            if cur is None:
                continue
            m = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if m and not line.startswith("    "):
                k, v = m.group(1), m.group(2)
                v = re.sub(r"\s+#.*$", "", v) if not v.startswith("[") else v
                if v.strip() in (">", "|"):
                    cur[k] = ""
                    folded_key = k
                else:
                    cur[k] = _scalar(v)
                    folded_key = None
                continue
            if folded_key and line.startswith("    "):
                cur[folded_key] = (cur[folded_key] + " " + line.strip()).strip()
        if cur:
            entries.append(cur)
    return entries


def snapshot(axis: str) -> dict:
    src = VAULT_VOCAB / f"{axis}.md"
    md = src.read_text(encoding="utf-8")
    m = re.search(r"^updated:\s*(\S+)", md, re.M)
    return {
        "axis": axis,
        # A repo-relative path: an absolute one names the operator's home directory, which
        # is exactly what wichaa's publish-time privacy gate refuses to ship.
        "source": f"wichaa-vault/_meta/vocab/{axis}.md",
        "vault_updated": m.group(1) if m else None,
        "entries": parse_entries(md),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not VAULT_VOCAB.exists():
        print(f"vault vocab not found at {VAULT_VOCAB}; snapshot left as is")
        return 0 if all((VOCAB / f"{x}.json").exists() for x in AXES) else 2
    stale = 0
    for axis in AXES:
        new = snapshot(axis)
        out = VOCAB / f"{axis}.json"
        if a.check:
            old = jload(out) if out.exists() else None
            if not old or old.get("entries") != new["entries"]:
                print(f"STALE {axis}")
                stale += 1
            continue
        jdump(new, out)
        keys = [e.get("key") for e in new["entries"]]
        print(f"{axis}: {len(keys)} entries → {out.name}  {keys}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
