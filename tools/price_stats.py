#!/usr/bin/env python3
"""price_stats.py — what the commerce corpus actually says about price, per kind and per axis.

Reads catalog.db (method='commerce', 15,295 priced Lazada Thailand listings, all THB) and
each record's own market.search / market.excludes terms — the same delete-then-test rule the
rest of the project uses — and writes data/analysis/price_stats.json:

  overall      n, min, quartiles, p90, p99, max, mean, and a log-decade histogram
  kinds        per record: n, median, IQR, p90, and its class / resident / region / form
  classes      per class: kinds, listings, median of the kind medians, and the pooled median
  materials    per vault material key (pooled across the kinds that carry it)
  functions    per vault function key
  keywords     the words the trade prices on: รุ่นแรก, แท้, ใบเซอร์, หลวงพ่อ, กรุ, เลี่ยม…

Every figure is a listing-TITLE match: it says what sellers ask for objects they describe
with that word, never what a piece is worth. The corpus is retail — median ฿129 — so it
cannot see the dealer or sian tiers at all, and says so in the file.

    python3 tools/price_stats.py
"""
from __future__ import annotations

import math
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, CATALOG_DB, DATA, jdump, jload, load_vocab  # noqa: E402

OUT = DATA / "analysis" / "price_stats.json"

# The words a Thai listing uses when it is pricing something other than the object itself.
KEYWORDS = [
    ("รุ่นแรก", "first issue", []),
    ("แท้", "genuine (claimed)", ["แท้จริง"]),
    ("ใบเซอร์", "certificate", []),
    ("บัตรรับรอง", "certification card", []),
    ("หลวงพ่อ", "Luang Pho (abbot)", []),
    ("หลวงปู่", "Luang Pu (elder monk)", []),
    ("เกจิ", "famous monk", []),
    ("วัด", "temple named", []),
    ("กรุ", "cache find", ["กรุง", "เครื่องกรุ"]),
    ("ปลุกเสก", "consecrated (stated)", []),
    ("พิธี", "ceremony named", []),
    ("เลี่ยม", "cased / framed", []),
    ("กรอบทอง", "gold frame", []),
    ("กล่องเดิม", "original box", []),
    ("พิมพ์นิยม", "preferred mould", []),
    ("ตำหนิ", "die flaw named", []),
    ("สร้างน้อย", "low mintage", []),
    ("นำเข้า", "imported", []),
]


def q(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return vals[int(k)] if lo == hi else vals[lo] * (hi - k) + vals[hi] * (k - lo)


def stats(vals: list[float]) -> dict:
    v = sorted(vals)
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": round(v[0], 2), "p25": round(q(v, .25), 2), "median": round(q(v, .5), 2),
            "p75": round(q(v, .75), 2), "p90": round(q(v, .9), 2), "p99": round(q(v, .99), 2),
            "max": round(v[-1], 2), "mean": round(statistics.fmean(v), 2)}


def survives(text: str, term: str, excludes) -> bool:
    for ex in excludes or []:
        text = text.replace(ex, "")
    return term in text


def main() -> int:
    if not CATALOG_DB.exists():
        raise SystemExit(f"catalog.db not found at {CATALOG_DB}")
    if not (BUILD / "api" / "kinds.json").exists():
        raise SystemExit("build/api/kinds.json missing — run tools/build.py first")
    con = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro&immutable=1", uri=True)
    rows = [(f"{t or ''} {e or ''}", float(p)) for t, e, p in con.execute(
        "SELECT title_thai, title_english, price_value FROM items "
        "WHERE method='commerce' AND price_value IS NOT NULL AND price_value > 0")]
    con.close()
    prices = [p for _, p in rows]
    t0 = time.time()

    # log-decade histogram — the shape of a market whose max is 11,600× its median
    hist = []
    for d in range(0, 7):
        lo, hi = 10 ** d, 10 ** (d + 1)
        n = sum(1 for p in prices if lo <= p < hi)
        if n:
            hist.append({"low": lo, "high": hi, "n": n, "share": round(100 * n / len(prices), 2),
                         "label": f"฿{lo:,}–{hi:,}"})

    recs = jload(BUILD / "api" / "kinds.json")["kinds"]
    vocab = {a: load_vocab(a) for a in ("classes", "materials", "functions")}
    kinds, by_class, by_mat, by_fn = [], {}, {}, {}
    for r in recs:
        m = r.get("market") or {}
        terms, ex = m.get("search") or [], m.get("excludes") or []
        if not terms:
            continue
        vals = [p for t, p in rows if any(survives(t, s, ex) for s in terms)]
        st = stats(vals)
        if not st["n"]:
            continue
        cf = r["class_facts"]
        k = {**st, "id": r["id"], "label_th": r["names"]["th"], "label_en": r["names"]["en"],
             "cls": r["axes"].get("class"), "cls_th": cf.get("term"), "resident": cf.get("resident"),
             "upkeep": cf.get("upkeep"), "form": r["form"]["type"], "region": r["region"],
             "images": len(r.get("images") or []), "level": r.get("level", "kind")}
        kinds.append(k)
        by_class.setdefault(r["axes"].get("class") or "unplaced", []).append((k, vals))
        for mk in r["axes"].get("materials") or []:
            by_mat.setdefault(mk, []).append((k, vals))
        for fk in r["axes"].get("functions") or []:
            by_fn.setdefault(fk, []).append((k, vals))

    def agg(d: dict, vocab_key: str | None) -> list[dict]:
        out = []
        for key, pairs in d.items():
            pooled = [p for _, vals in pairs for p in vals]
            meds = sorted(k["median"] for k, _ in pairs)
            e = (vocab.get(vocab_key) or {}).get(key) if vocab_key else None
            unplaced = key == "unplaced"
            out.append({"key": key, "label_th": ("ยังไม่ชี้ขาด" if unplaced else ((e or {}).get("term") or key)),
                        "label_en": ("left to a knower" if unplaced else ((e or {}).get("en_gloss") or "")),
                        "kinds": len(pairs), "listings": len(pooled), "median_pooled": round(q(sorted(pooled), .5), 2),
                        "median_of_kind_medians": round(q(meds, .5), 2), "min_kind_median": meds[0], "max_kind_median": meds[-1],
                        **({"resident": (e or {}).get("resident"), "upkeep": (e or {}).get("upkeep")} if vocab_key == "classes" else {}),
                        **({"dating_signal": (e or {}).get("dating_signal"), "counterfeit_pressure": (e or {}).get("counterfeit_pressure")} if vocab_key == "materials" else {})})
        return sorted(out, key=lambda r: -r["median_of_kind_medians"])

    keywords = []
    all_median = q(sorted(prices), .5)
    for th, en, ex in KEYWORDS:
        vals = [p for t, p in rows if survives(t, th, ex)]
        if len(vals) >= 3:
            st = stats(vals)
            keywords.append({**st, "label_th": th, "label_en": en, "ratio_to_all": round(st["median"] / all_median, 2)})
    keywords.sort(key=lambda r: -r["median"])

    out = {
        "built": time.strftime("%Y-%m-%d"),
        "source": "manuscript-crawler catalog.db · items where method='commerce' · Lazada Thailand listing titles",
        "caveat": ("Every figure is a match on a listing TITLE: it reports what sellers ask for objects they "
                   "describe with that word, never what a piece is worth. This is the retail tier — the dealer, "
                   "sian and investment tiers do not list here and are invisible in these numbers."),
        "overall": {**stats(prices), "currency": "THB", "histogram_by_decade": hist},
        "kinds": sorted(kinds, key=lambda k: -k["median"]),
        "classes": agg(by_class, "classes"),
        "materials": agg(by_mat, "materials"),
        "functions": agg(by_fn, "functions"),
        "keywords": keywords,
    }
    jdump(out, OUT)
    print(f"price_stats: {len(prices):,} listings · {len(kinds)} kinds priced · {len(out['classes'])} classes · "
          f"{len(keywords)} keywords · median ฿{out['overall']['median']:,.0f} → {OUT}  ({time.time()-t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
