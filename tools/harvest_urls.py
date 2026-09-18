#!/usr/bin/env python3
"""harvest_urls.py — pull free-licensed pictures from sources other than Commons.

Input: a candidates file, data/images/_hunt/urls.json, a list of
  {"kind": <record id>, "url": <direct image URL>, "page": <landing page>, "title": ...,
   "license": "CC BY 2.0" | "CC0" | ..., "license_url": ..., "author": ..., "source": "flickr"|"museum",
   "view": "obverse"|"in-situ"|"group"|"other", "note": ...}
built by the hunt scripts (Openverse for Flickr, the Smithsonian and Europeana APIs for museums).
Each entry is downloaded once (content-addressed by sha256, so a re-run costs nothing),
a sidecar .json is written beside the file, and with --apply the picture joins the record's
images[] (idempotent on url). The licence allowlist is the same as everywhere else: CC0,
public domain, CC BY, CC BY-SA. Anything else is refused here and again by validate.py.

    python3 tools/harvest_urls.py            # download, report
    python3 tools/harvest_urls.py --apply    # and merge into the records
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, KINDS, jdump, jload, load_kinds  # noqa: E402

FREE = re.compile(r"^(CC0(\s*1\.0)?|Public domain|PD(-[A-Za-z0-9-]+)?|CC[- ]BY(-SA)?(\s*[1-4]\.[0-9])?|FAL(\s*1\.[0-9])?)$", re.I)
UA = "amulet-essentials/0.1 (https://wichaa.net; research catalogue of Thai sacred objects)"
CANDS = IMAGES / "_hunt" / "urls.json"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    return b""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--kinds", nargs="*")
    a = ap.parse_args()
    cands = jload(CANDS) if CANDS.exists() else []
    recs = {r["id"]: r for r in load_kinds()}
    have_urls = {im.get("url") for r in recs.values() for im in r.get("images") or []}
    added: dict[str, list] = {}
    skipped = 0
    for c in cands:
        if a.kinds and c["kind"] not in a.kinds:
            continue
        rec = recs.get(c["kind"])
        if not rec or not FREE.match((c.get("license") or "").strip()) or c["url"] in have_urls:
            skipped += 1
            continue
        try:
            data = fetch(c["url"])
        except Exception as e:  # noqa: BLE001
            print(f"  ! {c['kind']} {c['url'][:60]}: {e}")
            continue
        if len(data) < 8_000:
            skipped += 1
            continue
        sha = hashlib.sha256(data).hexdigest()
        ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        slug = re.sub(r"[^a-z0-9]+", "-", (c.get("title") or "")[:40].lower()).strip("-")
        rel = f"{c['kind']}/{c['kind']}-{c.get('source','web')}{('-' + slug) if slug else ''}-{sha[:6]}{ext}"
        dest = IMAGES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        entry = {"file": rel, "source": c.get("source", "museum"), "title": c.get("title", ""), "url": c["url"], "page_url": c.get("page", ""),
                 "license": c["license"], "license_url": c.get("license_url", ""), "author": c.get("author", ""), "credit": c.get("credit", ""),
                 "view": c.get("view", "other"), "alt_th": rec["names"]["th"], "alt_en": f"{rec['names']['en']} — {c.get('title','')}"[:160],
                 "sha256": sha}
        jdump({**entry, "note": c.get("note", "")}, dest.with_suffix(dest.suffix + ".json"))
        added.setdefault(c["kind"], []).append(entry)
        have_urls.add(c["url"])
        print(f"  + {rel}  [{c['license']}]  {(c.get('author') or '')[:30]}")
    if a.apply:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from harvest_commons import set_primary
        for kid, entries in added.items():
            rec = recs[kid]
            rec.setdefault("images", []).extend(entries)
            set_primary(rec)
            jdump({k: v for k, v in rec.items() if not k.startswith("_")}, KINDS / f"{kid}.json")
    print(f"{sum(len(v) for v in added.values())} picture(s) for {len(added)} kind(s){' merged' if a.apply else ' downloaded (add --apply to merge)'} · {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
