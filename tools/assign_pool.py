#!/usr/bin/env python3
"""assign_pool.py — route a pool of generic Commons hits to the kinds they name.

Generic searches — พระพิมพ์, เหรียญพระ, รูปหล่อ, วัตถุมงคล, "Thai votive tablet", the
Tropenmuseum uploads — return files whose titles name a kind the per-kind hunt never
queried for, or name it in a form the hunt did not try. This pass scores every pooled
file against every record with the hunt's relevance rule (a name or alias of the kind in
the title or description) and hands it to the single best record when exactly one kind is
named. A file that names two kinds is left alone: it is a group photograph, and a group
photograph is evidence for nobody (the dedupe rule).

    python3 tools/assign_pool.py <pool.json> [--apply]
       pool.json = {"query": ["File:…", …], …} as written by the extra-queries sweep
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, KINDS, jdump, jload, load_kinds  # noqa: E402
from hunt_commons import file_info, relevance  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pool")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min", type=float, default=2.0, help="relevance floor: 2.0 = at least one name matched")
    a = ap.parse_args()
    pool = json.loads(Path(a.pool).read_text(encoding="utf-8"))
    titles = sorted({t for hits in pool.values() for t in hits})
    recs = load_kinds()
    held = {im.get("title") for r in recs for im in r.get("images") or []}
    wanted = {t for r in recs for t in (r.get("media") or {}).get("commons_files") or []}
    titles = [t for t in titles if t not in held and t not in wanted]
    print(f"{len(titles)} pooled titles not yet held or queued")
    info = [f for f in file_info(titles) if f.get("title") and f["free"] and not (f.get("mime") or "").endswith("svg")]
    print(f"{len(info)} free")
    assigned: dict[str, list] = {}
    ambiguous = 0
    for f in info:
        scores = [(relevance(f, r), r) for r in recs]
        top = [s for s in scores if s[0] >= a.min]
        if not top:
            continue
        top.sort(key=lambda s: -s[0])
        names_hit = [r["id"] for s, r in top if s >= 2.0]
        if len(set(names_hit)) > 1:
            ambiguous += 1
            continue
        assigned.setdefault(top[0][1]["id"], []).append((top[0][0], f))
    for kid, fs in sorted(assigned.items()):
        fs.sort(key=lambda x: -x[0])
        print(f"  {kid:<22} +{len(fs)}  " + " | ".join(f"{f['title'][5:38]}" for _, f in fs[:3]))
    print(f"{sum(len(v) for v in assigned.values())} assignable · {ambiguous} name more than one kind (left alone)")
    if a.apply:
        by_id = {r["id"]: r for r in recs}
        for kid, fs in assigned.items():
            r = by_id[kid]
            media = r.setdefault("media", {})
            cur = list(media.get("commons_files") or [])
            media["commons_files"] = cur + [f["title"] for _, f in fs if f["title"] not in cur]
            jdump({k: v for k, v in r.items() if not k.startswith("_")}, KINDS / f"{kid}.json")
        print("queued into media.commons_files — run harvest_commons.py --harvest <ids> --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
