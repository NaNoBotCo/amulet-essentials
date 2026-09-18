#!/usr/bin/env python3
"""build.py — records + vault snapshot + catalogue counts → build/ (JSON API, SQLite, search tables).

Order: validate → enrich → write. Nothing is written if validation fails.

Outputs (all regenerated, never hand-edited):
  build/api/kinds.json             every enriched record
  build/api/kind/<id>.json         one per record
  build/api/index.json             directory: id, names, class, region, image, counts
  build/api/vocab/*.json           class / material / function / regions snapshots
  build/api/sources.json           the source registry
  build/essentials.db              SQLite: kinds, fields (with provenance), images, market, FTS5 trigram
  build/searchdocs.json            one bilingual document per record, for embed.py
  data/search/amulets.thesaurus.json + amulets.segdict.txt   mined from the records for search-core

    python3 tools/build.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BUILD, CATALOG_DB, DATA, IMAGES, SOURCES, TIER_LABEL_EN, TIER_LABEL_TH,  # noqa: E402
                    jdump, jload, load_kinds, load_vocab, load_wats)
from validate import validate_all  # noqa: E402

SEARCH_DIR = DATA / "search"


# ------------------------------------------------------------------ enrichment

def class_facts(cls: dict | None) -> dict:
    if not cls:
        return {"key": None, "term": "ยังไม่ชี้ขาด", "en": "left to a knower", "resident": None, "upkeep": None,
                "provenance_sensitivity": None, "definition": "The vault vocabulary does not place this kind; the refusal is recorded, not papered over."}
    return {k: cls.get(k) for k in ("key", "term", "roman", "en_gloss", "resident", "upkeep", "provenance_sensitivity", "definition", "confidence")}


def _terms(keys: list[str], vocab: dict) -> list[dict]:
    out = []
    for k in keys:
        e = vocab.get(k)
        out.append({"key": k, "term": e.get("term") if e else k, "roman": e.get("roman") if e else "",
                    "en": e.get("en_gloss") if e else "", "definition": e.get("definition", "") if e else ""})
    return out


def survives(text: str, term: str, excludes: list[str]) -> bool:
    """axis_match rule: delete the excluded strings, THEN test."""
    for ex in excludes:
        text = text.replace(ex, "")
    return term in text


def market_stats(recs: list[dict]) -> dict:
    """Listing counts and price spread per kind from catalog.db titles. Catalogue tier."""
    if not CATALOG_DB.exists():
        return {}
    con = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro&immutable=1", uri=True)
    rows = con.execute("SELECT COALESCE(title_thai,'') || ' ' || COALESCE(title_english,''), price_value "
                       "FROM items WHERE method='commerce'").fetchall()
    con.close()
    out = {}
    for r in recs:
        m = r.get("market") or {}
        terms, ex = m.get("search") or [], m.get("excludes") or []
        if not terms:
            continue
        prices = [p for t, p in rows if any(survives(t, s, ex) for s in terms) and p]
        n = sum(1 for t, _ in rows if any(survives(t, s, ex) for s in terms))
        if n:
            ps = sorted(float(p) for p in prices)
            lo, hi = (ps[len(ps) // 10], ps[(len(ps) * 9) // 10]) if len(ps) >= 10 else (ps[0], ps[-1]) if ps else (None, None)
            out[r["id"]] = {"listings": n, "priced": len(ps), "median_thb": statistics.median(ps) if ps else None,
                            "typical_thb": [lo, hi], "source": "s:catalog-db", "tier": "catalogue",
                            "note": "title matches only; delete-then-test excludes applied"}
        else:
            out[r["id"]] = {"listings": 0, "priced": 0, "median_thb": None, "typical_thb": [None, None],
                            "source": "s:catalog-db", "tier": "catalogue", "note": "no listing title carries this term"}
    return out


def enrich(rec: dict, vocab: dict, market: dict, wats: dict) -> dict:
    r = {k: v for k, v in rec.items() if not k.startswith("_")}
    ax = r["axes"]
    r["class_facts"] = class_facts(vocab["classes"].get(ax.get("class")))
    r["function_terms"] = _terms(ax.get("functions", []), vocab["functions"])
    r["material_terms"] = _terms(ax.get("materials", []), vocab["materials"])
    r["region_terms"] = [dict(vocab["regions"].get(k) or {"key": k, "th": k, "en": k}) for k in r["region"]]
    r["market_stats"] = market.get(r["id"])
    slug = (r.get("origin") or {}).get("wat_slug")
    if slug and slug in wats:
        r["origin"]["wat_url"] = f"https://wichaa.net/place/{slug}/"
    prim = next((im for im in r.get("images", []) if im.get("primary")), (r.get("images") or [None])[0])
    r["primary_image"] = prim
    r["tier_labels"] = {"en": TIER_LABEL_EN, "th": TIER_LABEL_TH}
    return r


# ------------------------------------------------------------------ search docs

def search_doc(r: dict) -> str:
    n = r["names"]
    al = n.get("aliases") or {}
    parts = [
        " · ".join([n["th"], n["roman"], n["en"]] + list((n.get("other_scripts") or {}).values()) + al.get("th", []) + al.get("roman", []) + al.get("en", [])),
        r["text"].get("what_th", ""), r["text"].get("what_en", ""),
        " ".join(f"{i.get('th','')} {i.get('en','')}" for i in r.get("iconography", [])),
        f"{r['form'].get('shape_th','')} {r['form'].get('shape_en','')} {r['form'].get('obverse_en','')}",
        " ".join(filter(None, [(r.get("origin") or {}).get(k, "") for k in ("wat_th", "wat_en", "maker_th", "maker_en", "place_th", "place_en", "era_en")])),
        f"{r['class_facts'].get('term','')} {r['class_facts'].get('en_gloss','')}",
        " ".join(f"{t['term']} {t['en']}" for t in r["function_terms"] + r["material_terms"]),
        " ".join(f"{t.get('th','')} {t.get('en','')}" for t in r["region_terms"]),
        r["text"].get("keeping_en", ""),
    ]
    return "\n".join(p.strip() for p in parts if p and p.strip())


def mine_search_tables(recs: list[dict], vocab: dict):
    """Synonymy groups + Thai segmentation words from the records themselves (never hand-curated)."""
    groups, words = [], set()
    thai = re.compile(r"[฀-๿]{2,}")
    for r in recs:
        n = r["names"]
        al = n.get("aliases") or {}
        g = [n["th"], n["roman"].lower(), n["en"].lower()] + al.get("th", []) + [a.lower() for a in al.get("roman", []) + al.get("en", [])]
        groups.append(sorted(set(x for x in g if x)))
        for s in g:
            words.update(thai.findall(s))
        for t in r["text"].values():
            words.update(thai.findall(t))
    for axis in ("classes", "materials", "functions"):
        for e in vocab[axis].values():
            g = [e.get("term", ""), (e.get("roman") or "").lower(), (e.get("en_gloss") or "").lower()]
            g = [x for x in g if x and len(x.split()) <= 3]
            if len(g) >= 2:
                groups.append(sorted(set(g)))
            words.update(thai.findall(e.get("term", "")))
            for m in e.get("members", []) or []:
                words.update(thai.findall(m))
    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    jdump({"note": "mined by build.py from data/kinds + data/vocab — synonymy only", "groups": groups},
          SEARCH_DIR / "amulets.thesaurus.json", indent=0)
    (SEARCH_DIR / "amulets.segdict.txt").write_text(
        "# Thai words present in the amulet records and vocab\n" + "\n".join(sorted(words)) + "\n", encoding="utf-8")
    return len(groups), len(words)


# ------------------------------------------------------------------ sqlite

def write_db(recs: list[dict]):
    db = BUILD / "essentials.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE kinds(id TEXT PRIMARY KEY, level TEXT, parent TEXT, name_th TEXT, name_roman TEXT, name_en TEXT,
                       class TEXT, resident TEXT, upkeep TEXT, region TEXT, confidence TEXT, updated TEXT, json TEXT);
    CREATE TABLE fields(kind_id TEXT, path TEXT, value TEXT, tier TEXT, source TEXT, note TEXT);
    CREATE INDEX fields_kind ON fields(kind_id); CREATE INDEX fields_path ON fields(path);
    CREATE TABLE images(kind_id TEXT, file TEXT, source TEXT, license TEXT, author TEXT, page_url TEXT, view TEXT, "primary" INTEGER);
    CREATE TABLE market(kind_id TEXT PRIMARY KEY, listings INTEGER, priced INTEGER, median_thb REAL, typical_lo REAL, typical_hi REAL);
    CREATE TABLE confusable(kind_id TEXT, other_id TEXT, tell_th TEXT, tell_en TEXT);
    CREATE VIRTUAL TABLE fts USING fts5(id UNINDEXED, name, text, tokenize='trigram');
    """)

    def walk(prefix, node, out):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(f"{prefix}.{k}" if prefix else k, v, out)
        elif isinstance(node, list):
            out.append((prefix, json.dumps(node, ensure_ascii=False)))
        elif node is not None:
            out.append((prefix, str(node)))

    for r in recs:
        prov = r.get("provenance", {})
        default = prov.get("default", {})
        overrides = prov.get("fields", {})

        def tier_for(path):
            best = None
            for p, v in overrides.items():
                if path == p or path.startswith(p + "."):
                    if best is None or len(p) > len(best[0]):
                        best = (p, v)
            return best[1] if best else default

        con.execute("INSERT INTO kinds VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            r["id"], r["level"], r.get("parent"), r["names"]["th"], r["names"]["roman"], r["names"]["en"],
            r["axes"].get("class"), r["class_facts"].get("resident"), r["class_facts"].get("upkeep"),
            ",".join(r["region"]), r["confidence"], r["updated"], json.dumps(r, ensure_ascii=False)))
        flat: list = []
        for key in ("names", "region", "axes", "form", "iconography", "origin", "diagnostics", "text", "market"):
            if key in r:
                walk(key, r[key], flat)
        for path, val in flat:
            t = tier_for(path)
            con.execute("INSERT INTO fields VALUES (?,?,?,?,?,?)", (r["id"], path, val, t.get("tier"), t.get("source", ""), t.get("note", "")))
        for im in r.get("images", []):
            con.execute("INSERT INTO images VALUES (?,?,?,?,?,?,?,?)", (r["id"], im["file"], im["source"], im["license"], im.get("author", ""), im.get("page_url", ""), im["view"], 1 if im.get("primary") else 0))
        ms = r.get("market_stats")
        if ms:
            con.execute("INSERT INTO market VALUES (?,?,?,?,?,?)", (r["id"], ms["listings"], ms["priced"], ms["median_thb"], ms["typical_thb"][0], ms["typical_thb"][1]))
        for c in r.get("confusable_with", []):
            con.execute("INSERT INTO confusable VALUES (?,?,?,?)", (r["id"], c["id"], c.get("tell_th", ""), c["tell_en"]))
        con.execute("INSERT INTO fts VALUES (?,?,?)", (r["id"], " ".join([r["names"]["th"], r["names"]["roman"], r["names"]["en"]]), r["_searchdoc"]))
    con.commit()
    con.close()
    return db


# ------------------------------------------------------------------ main

def main() -> int:
    if validate_all() != 0:
        print("build refused: fix the errors above")
        return 1
    t0 = time.time()
    vocab = {a: load_vocab(a) for a in ("classes", "materials", "functions")}
    vocab["regions"] = {e["key"]: e for e in jload(DATA / "vocab" / "regions.json")["entries"]}
    recs_raw = load_kinds()
    market = market_stats(recs_raw)
    wats = load_wats()
    recs = [enrich(r, vocab, market, wats) for r in recs_raw]
    for r in recs:
        r["_searchdoc"] = search_doc(r)
    ng, nw = mine_search_tables(recs, vocab)

    api = BUILD / "api"
    for r in recs:
        jdump({k: v for k, v in r.items() if not k.startswith("_")}, api / "kind" / f"{r['id']}.json")
    jdump({"built": time.strftime("%Y-%m-%d"), "count": len(recs),
           "kinds": [{k: v for k, v in r.items() if not k.startswith("_")} for r in recs]}, api / "kinds.json")
    jdump({"built": time.strftime("%Y-%m-%d"), "count": len(recs), "kinds": [{
        "id": r["id"], "level": r["level"], "parent": r.get("parent"), "names": r["names"], "class": r["axes"].get("class"),
        "class_term": r["class_facts"].get("term"), "resident": r["class_facts"].get("resident"), "upkeep": r["class_facts"].get("upkeep"),
        "region": r["region"], "form": r["form"]["type"], "image": (r["primary_image"] or {}).get("file"),
        "listings": (r.get("market_stats") or {}).get("listings"), "what_en": r["text"]["what_en"], "what_th": r["text"].get("what_th", ""),
        "confidence": r["confidence"], "needs_verification": r.get("needs_verification", False), "updated": r["updated"],
    } for r in recs]}, api / "index.json")
    for a in ("classes", "materials", "functions", "regions"):
        jdump(jload(DATA / "vocab" / f"{a}.json"), api / "vocab" / f"{a}.json")
    jdump(jload(SOURCES), api / "sources.json")
    jdump({"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "docs": [{"id": r["id"], "text": r["_searchdoc"]} for r in recs]},
          BUILD / "searchdocs.json")
    db = write_db(recs)
    n_img = sum(len(r.get("images", [])) for r in recs)
    print(f"built {len(recs)} kinds · {n_img} images · {sum(1 for r in recs if r.get('market_stats'))} with market stats · "
          f"thesaurus {ng} groups · segdict {nw} words · {db.name} · {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
