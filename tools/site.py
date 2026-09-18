#!/usr/bin/env python3
"""site.py — build/api → build/site: a static site that people and bots can both read.

People: a 1997-directory front page (Term (count) links, hierarchy on the page), one page
per kind with both languages visible (no toggle hides content), large type, high contrast,
theme-aware, motion gated behind prefers-reduced-motion, no external requests.

Bots: JSON-LD on every page (Dataset + DefinedTermSet on the front, DefinedTerm + ImageObject
with licence per kind), hreflang + rel=alternate JSON links, robots.txt that ALLOWS
everything and says so with Content-Signal, sitemap.xml with lastmod, llms.txt and
llms-full.txt, Atom feed, OpenSearch description, CSV + JSONL dumps, the whole /api tree.

    python3 tools/site.py                     # SITE_URL defaults to https://wichaa.net/amulets
    SITE_URL=https://example.org python3 tools/site.py
"""
from __future__ import annotations

import csv
import html
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, DATA, IMAGES, VENDOR, jload  # noqa: E402

SITE = BUILD / "site"
API = BUILD / "api"
SITE_URL = os.environ.get("SITE_URL", "https://wichaa.net/amulets").rstrip("/")
SITE_NAME_EN = "Amulet Essentials"
SITE_NAME_TH = "สารบบเครื่องราง"
# When IMAGE_BASE is set (e.g. https://wichaa.net/img) pictures are NOT copied into the
# site; every <img>, JSON-LD contentUrl and sitemap entry points at IMAGE_BASE/<sha256><ext>
# — the content-addressed store the wichaa router serves from R2, immutable forever.
IMAGE_BASE = os.environ.get("IMAGE_BASE", "").rstrip("/")
# Rendered share cards (publishing/cards/<route>.png convention): when a kind's card
# exists its page's og:image points at card.png instead of the raw picture.
CARDS_DIR = Path(os.environ["CARDS_DIR"]) if os.environ.get("CARDS_DIR") else None
DATA_LICENSE = "https://creativecommons.org/licenses/by/4.0/"   # the records' own licence — Nan's call; default CC BY 4.0
AUTHOR = {"@type": "Person", "name": "Nan Peacock", "url": "https://wichaa.net"}
FORM_TH = {"tablet": "พระพิมพ์/แผ่น", "figure": "รูปหล่อ/รูปปั้น", "medallion": "เหรียญ", "coin": "เหรียญกษาปณ์", "tube": "ตะกรุด/หลอด",
           "cloth": "ผ้า", "blade": "มีด/ของมีคม", "shell": "เปลือกหอย/เบี้ย", "oil": "น้ำมัน", "wax": "ขี้ผึ้ง", "plant": "ว่าน/พืช",
           "natural": "ของธรรมชาติ", "locket": "ล็อกเก็ต", "bead": "ลูกประคำ", "ring": "แหวน", "vessel": "ภาชนะ", "other": "อื่น ๆ"}

E = html.escape


def rel(depth: int) -> str:
    return "../" * depth


def img_src(im: dict, depth: int) -> str:
    """Where a picture lives on this build: local copy, or the content-addressed store."""
    if IMAGE_BASE and im.get("sha256"):
        return f"{IMAGE_BASE}/{im['sha256']}{Path(im['file']).suffix.lower()}"
    return f"{rel(depth)}images/{im['file']}"


def img_abs(im: dict) -> str:
    if IMAGE_BASE and im.get("sha256"):
        return f"{IMAGE_BASE}/{im['sha256']}{Path(im['file']).suffix.lower()}"
    return f"{SITE_URL}/images/{im['file']}"


CSS = """
:root{--bg:#fbf8f2;--ink:#1c1a17;--mute:#5d574d;--line:#e3dccd;--card:#fff;--gold:#a67c1a;--teal:#1f6f6b;--chip:#f1ebdd;--focus:#2b6cb0}
@media (prefers-color-scheme: dark){:root{--bg:#141311;--ink:#f1ede4;--mute:#b8b0a2;--line:#2c2924;--card:#1c1a17;--gold:#e0b64a;--teal:#6fc7c2;--chip:#242119;--focus:#8ab4f8}}
*{box-sizing:border-box}html{font-size:19px}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"Noto Sans Thai","Thonburi","Segoe UI",Roboto,sans-serif;line-height:1.55}
a{color:var(--teal);text-decoration-thickness:.08em;text-underline-offset:.15em}a:hover{color:var(--gold)}
a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
main{max-width:64rem;margin:0 auto;padding:1.2rem 1rem 4rem}header.top{border-bottom:1px solid var(--line);padding:.6rem 1rem;display:flex;gap:1rem;flex-wrap:wrap;align-items:baseline;max-width:64rem;margin:0 auto}
header.top a{text-decoration:none}header.top .brand{font-weight:700;letter-spacing:.01em}nav.crumbs{font-size:.85rem;color:var(--mute)}@media(max-width:480px){header.top nav.crumbs{font-size:.78rem}html{font-size:18px}}
h1{font-size:1.9rem;line-height:1.2;margin:.4rem 0 .2rem}h1 .roman{font-weight:400;color:var(--mute);font-size:1.1rem;display:block}h2{font-size:1.25rem;margin:1.6rem 0 .5rem;border-bottom:1px solid var(--line);padding-bottom:.2rem}h3{font-size:1.05rem;margin:1rem 0 .3rem}
.lede{font-size:1.15rem;margin:.2rem 0 1rem}.th{font-family:"Noto Sans Thai","Thonburi",-apple-system,sans-serif}.mute{color:var(--mute)}
.dir{display:grid;grid-template-columns:repeat(auto-fill,minmax(19rem,1fr));gap:1.4rem 2.5rem;align-items:start}.dir section{margin:0}
.dir h2{margin:.2rem 0 .3rem;border:0;font-size:1.05rem}.dir ul{list-style:none;margin:0;padding:0 0 0 .6rem}.dir li{margin:.15rem 0}.count{color:var(--mute);font-size:.85em}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:.05rem .6rem;font-size:.8rem;margin:.1rem .2rem .1rem 0;color:var(--ink)}
.tier-catalogue{border-color:var(--teal)}.tier-cited{border-color:var(--focus)}.tier-tradition{border-color:var(--gold)}.tier-inference{border-style:dashed}.tier-field{border-color:#b5541c}
table{border-collapse:collapse;width:100%;margin:.4rem 0 1rem;font-size:.95rem}th,td{text-align:left;vertical-align:top;padding:.45rem .5rem;border-bottom:1px solid var(--line)}th{width:30%;color:var(--mute);font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.9rem;position:relative}
.card a.t{font-weight:700;text-decoration:none;font-size:1.05rem}.card p{margin:.3rem 0 0;font-size:.9rem;color:var(--mute)}
figure{margin:0 0 1rem;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.6rem}figure img{width:100%;height:auto;border-radius:8px;display:block}figcaption{font-size:.8rem;color:var(--mute);margin-top:.4rem}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(11rem,1fr));gap:.7rem}.gallery figure{margin:0}
.search{display:flex;gap:.5rem;margin:.6rem 0 1rem}.search input{flex:1;font:inherit;font-size:1.1rem;padding:.6rem .8rem;border:2px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink)}.search button{font:inherit;padding:.6rem 1rem;border-radius:10px;border:2px solid var(--teal);background:var(--teal);color:#fff;cursor:pointer}
.tierline{font-size:.9rem;color:var(--mute);margin:.2rem 0 .8rem}.legend{font-size:.85rem;color:var(--mute);border-top:1px solid var(--line);margin-top:2rem;padding-top:.6rem}
footer{max-width:64rem;margin:0 auto;padding:1rem;color:var(--mute);font-size:.85rem;border-top:1px solid var(--line)}
.bots{font-size:.85rem;color:var(--mute)}.bots a{margin-right:.8rem}
.cta{display:flex;gap:.6rem;flex-wrap:wrap;margin:.6rem 0 1rem}.btn{display:inline-block;padding:.6rem 1rem;border-radius:10px;background:var(--teal);color:#fff;text-decoration:none;font-weight:600;border:2px solid var(--teal)}.btn.ghost{background:var(--card);color:var(--ink);border-color:var(--line)}.btn:hover{color:#fff;filter:brightness(1.08)}.btn.ghost:hover{color:var(--ink);border-color:var(--teal)}
@media (prefers-reduced-motion: no-preference){.card{transition:transform .18s ease,box-shadow .18s ease}.card:hover{transform:translateY(-3px);box-shadow:0 10px 24px rgba(0,0,0,.08)}.search input{transition:box-shadow .2s}.search input:focus{box-shadow:0 0 0 4px color-mix(in srgb,var(--teal) 25%,transparent)}a{transition:color .15s}}
"""


def page(title: str, body: str, depth: int, desc: str = "", jsonld: list | None = None, canonical: str = "", extra_head: str = "") -> str:
    r = rel(depth)
    ld = "".join(f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>' for o in (jsonld or []))
    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc[:300])}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<meta name="color-scheme" content="light dark">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc[:200])}"><meta property="og:type" content="website">
{f'<link rel="canonical" href="{E(canonical)}">' if canonical else ''}
<link rel="alternate" hreflang="th" href="{E(canonical or SITE_URL + '/')}"><link rel="alternate" hreflang="en" href="{E(canonical or SITE_URL + '/')}"><link rel="alternate" hreflang="x-default" href="{E(canonical or SITE_URL + '/')}">
<link rel="manifest" href="{r}manifest.webmanifest">
<meta name="theme-color" content="#1f6f6b">
<link rel="icon" href="{r}icon.svg" type="image/svg+xml">
<link rel="search" type="application/opensearchdescription+xml" title="{E(SITE_NAME_EN)}" href="{r}opensearch.xml">
<link rel="alternate" type="application/atom+xml" title="{E(SITE_NAME_EN)} updates" href="{r}feed.xml">
{extra_head}
<style>{CSS}</style>
{ld}
</head>
<body>
<header class="top"><a class="brand" href="{r}index.html"><span class="th">{SITE_NAME_TH}</span> · {SITE_NAME_EN}</a>
<nav class="crumbs"><a href="{r}index.html">Directory</a> · <a href="{r}search/index.html">Search · ค้นหา</a> · <a href="{r}identify/index.html">Photograph it · ส่องภาพ</a> · <a href="{r}value/index.html">Price · ราคา</a> · <a href="{r}vocab/index.html">Vocabulary</a> · <a href="{r}sources/index.html">Sources</a> · <a href="{r}api/index.json">API</a> · <a href="{r}llms.txt">llms.txt</a></nav></header>
<main>
{body}
</main>
<footer>
<div class="bots">Machine-readable: <a href="{r}api/kinds.json">kinds.json</a> <a href="{r}kinds.jsonl">kinds.jsonl</a> <a href="{r}kinds.csv">kinds.csv</a> <a href="{r}llms-full.txt">llms-full.txt</a> <a href="{r}sitemap.xml">sitemap.xml</a> <a href="{r}feed.xml">feed.xml</a> <a href="{r}api/vocab/classes.json">vocab</a> <a href="{r}api/sources.json">sources</a></div>
<p>Records © Nan Peacock, licensed <a href="{DATA_LICENSE}">CC BY 4.0</a>. Images carry their own licences, stated beside each one. Emic term first; English is a gloss. Every field says where it came from.</p>
</footer>
</body>
</html>
"""


# ------------------------------------------------------------------ helpers

def tier_chip(tier: str, source: str = "") -> str:
    lab = {"catalogue": "Catalogue · จากคลัง", "cited": "Cited · อ้างอิง", "tradition": "Tradition · ตามประเพณี",
           "inference": "Inference · อนุมาน", "field": "Field · พบเห็นเอง"}.get(tier, tier or "")
    return f'<span class="chip tier-{E(tier)}" title="{E(source)}">{E(lab)}</span>'


def field_tier(rec: dict, path: str) -> dict:
    prov = rec.get("provenance", {})
    best = None
    for p, v in (prov.get("fields") or {}).items():
        if path == p or path.startswith(p + "."):
            if best is None or len(p) > len(best[0]):
                best = (p, v)
    return best[1] if best else prov.get("default", {})


def img_tag(im: dict, rec: dict, depth: int, lazy=True, n: int | None = None) -> str:
    src = img_src(im, depth)
    w, h = im.get("width") or 0, im.get("height") or 0
    dims = f' width="{w}" height="{h}"' if w and h else ""
    alt = im.get("alt_en") or rec["names"]["en"]
    cred = f"{im.get('author','')} · {im.get('license','')}".strip(" ·")
    link = im.get("page_url") or im.get("url") or ""
    cap = f'<a href="{E(link)}" rel="license noopener">{E(cred)}</a>' if link else E(cred)
    img = f'<img src="{E(src)}" alt="{E(alt)}"{dims}{" loading=lazy decoding=async" if lazy else ""}>'
    if n is not None:
        img = f'<a href="{rel(depth)}kind/{E(rec["id"])}/image/{n}/index.html">{img}</a>'
    return f'<figure>{img}<figcaption>{E(im.get("view",""))} · {cap}</figcaption></figure>'


def image_page(rec: dict, im: dict, n: int, sources: dict, by_id: dict | None = None) -> str:
    """One landing page per picture — what a reverse-image search lands on. The picture
    is the page: big, described in both languages, licensed on the spot, and one link
    from the full record."""
    nm = rec["names"]
    by_id = by_id or {}
    d = 4
    url = f"{SITE_URL}/kind/{rec['id']}/image/{n}/"
    src = img_abs(im)
    body = [f'<nav class="crumbs"><a href="{rel(d)}index.html">Directory</a> › <a href="../../index.html">{E(nm["th"])} · {E(nm["en"])}</a> › picture {n}</nav>',
            f'<h1><span class="th">{E(nm["th"])}</span> <span class="roman">{E(nm["roman"])} · {E(nm["en"])} — {E(im.get("view","picture"))}</span></h1>',
            img_tag(im, rec, d, lazy=False),
            cta(rec, d),
            f'<p class="lede th" lang="th">{E(rec["text"].get("what_th",""))}</p><p class="lede" lang="en">{E(rec["text"]["what_en"])}</p>',
            '<table>',
            f'<tr><th>Class · หมวด</th><td>{E(rec["class_facts"].get("term") or "ยังไม่ชี้ขาด")} <span class="mute">{E(rec["class_facts"].get("en_gloss") or "")}</span></td></tr>',
            f'<tr><th>Licence</th><td><a href="{E(im.get("license_url") or "")}" rel="license">{E(im.get("license",""))}</a> · {E(im.get("author",""))}</td></tr>',
            f'<tr><th>Source</th><td><a href="{E(im.get("page_url") or im.get("url") or "")}" rel="noopener">{E(im.get("title") or im.get("page_url") or im.get("source",""))}</a></td></tr>',
            f'<tr><th>Full record</th><td><a href="../../index.html">{E(nm["th"])} · {E(nm["en"])}</a> · <a href="{rel(d)}api/kind/{E(rec["id"])}.json">JSON</a></td></tr>',
            '</table>']
    conf = rec.get("confusable_with") or []
    if conf:
        body.append("<h2>How to tell it from · แยกจาก</h2><table>")
        for c in conf:
            o = by_id.get(c["id"])
            nm2 = f'<a href="{rel(d)}kind/{E(c["id"])}/index.html">{E(o["names"]["th"])} · {E(o["names"]["en"])}</a>' if o else E(c["id"])
            body.append(f'<tr><th>{nm2}</th><td><span class="th" lang="th">{E(c.get("tell_th",""))}</span><br><span lang="en">{E(c["tell_en"])}</span></td></tr>')
        body.append("</table>")
    ld = [{"@context": "https://schema.org", "@type": "ImageObject", "@id": url, "contentUrl": src, "url": url,
           "name": f"{nm['th']} · {nm['en']} — {im.get('view','')}", "caption": im.get("alt_en", ""), "description": rec["text"]["what_en"],
           "license": im.get("license_url") or im.get("license"), "acquireLicensePage": im.get("page_url", ""), "creditText": im.get("author", ""),
           "creator": {"@type": "Person", "name": im.get("author", "")}, "copyrightNotice": im.get("license", ""),
           "width": im.get("width"), "height": im.get("height"), "inLanguage": ["th", "en"],
           "about": {"@type": "DefinedTerm", "@id": f"{SITE_URL}/kind/{rec['id']}/", "name": nm["th"], "alternateName": nm["en"]},
           "representativeOfPage": True}]
    extra = f'<meta property="og:image" content="{E(src)}"><meta name="twitter:card" content="summary_large_image">'
    return page(f'{nm["th"]} · {nm["en"]} — picture {n}', "\n".join(body), d, f"{nm['en']} ({nm['th']}): {rec['text']['what_en']}", ld, url, extra)


def cta(rec: dict, depth: int) -> str:
    """The door a Google-Lens arrival needs: they are holding one, or a photo of one."""
    n = rec["names"]
    return (f'<p class="cta"><a class="btn" href="{rel(depth)}identify/index.html?kind={E(rec["id"])}">📷 '
            f'<span class="th" lang="th">ถือชิ้นนี้อยู่? ถ่ายรูปเทียบ</span> · Holding one? Photograph it to compare</a> '
            f'<a class="btn ghost" href="{rel(depth)}search/index.html?q={E(n["th"])}">🔍 ค้นหา · search {E(n["en"][:24])}</a></p>')


def wiki_links(rec: dict, sources: dict) -> list[str]:
    return [sources[s]["url"] for s in rec.get("sources", []) if s in sources and sources[s].get("type") == "wikipedia" and sources[s].get("url")]


# ------------------------------------------------------------------ JSON-LD

def kind_jsonld(rec: dict, sources: dict) -> list:
    url = f"{SITE_URL}/kind/{rec['id']}/"
    n = rec["names"]
    al = n.get("aliases") or {}
    term = {
        "@context": "https://schema.org", "@type": "DefinedTerm", "@id": url, "url": url,
        "name": n["th"], "alternateName": [n["en"], n["roman"]] + list((n.get("other_scripts") or {}).values()) + al.get("en", []) + al.get("roman", []) + al.get("th", []),
        "description": rec["text"]["what_en"],
        "inDefinedTermSet": {"@type": "DefinedTermSet", "@id": f"{SITE_URL}/#termset", "name": SITE_NAME_EN},
        "termCode": rec["id"],
        "inLanguage": ["th", "en"],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "class", "value": rec["class_facts"].get("term") or "unplaced"},
            {"@type": "PropertyValue", "name": "resident", "value": rec["class_facts"].get("resident") or "unplaced"},
            {"@type": "PropertyValue", "name": "upkeep", "value": rec["class_facts"].get("upkeep") or "unplaced"},
            {"@type": "PropertyValue", "name": "form", "value": rec["form"]["type"]},
            {"@type": "PropertyValue", "name": "materials", "value": ", ".join(t["term"] for t in rec["material_terms"])},
            {"@type": "PropertyValue", "name": "functions", "value": ", ".join(t["term"] for t in rec["function_terms"])},
            {"@type": "PropertyValue", "name": "region", "value": ", ".join(rec["region"])},
        ],
        "sameAs": wiki_links(rec, sources),
        "license": DATA_LICENSE,
        "creator": AUTHOR,
        "dateModified": rec["updated"],
    }
    imgs = []
    for im in rec.get("images", []):
        imgs.append({"@type": "ImageObject", "contentUrl": img_abs(im), "license": im.get("license_url") or im.get("license"),
                     "acquireLicensePage": im.get("page_url", ""), "creditText": im.get("author", ""),
                     "creator": {"@type": "Person", "name": im.get("author", "")}, "copyrightNotice": im.get("license", ""),
                     "name": im.get("alt_en", ""), "width": im.get("width"), "height": im.get("height")})
    if imgs:
        term["image"] = imgs
    return [term]


def index_jsonld(recs: list[dict]) -> list:
    ds = {
        "@context": "https://schema.org", "@type": "Dataset", "@id": f"{SITE_URL}/#dataset",
        "name": f"{SITE_NAME_EN} — kinds of Thai and Southeast Asian sacred objects",
        "alternateName": SITE_NAME_TH,
        "description": "One structured record per kind of amulet or charm (พระเครื่อง / เครื่องราง): emic Thai term, romanisation, English gloss, class (does anything live in it, what does the keeper owe it), material, function, form, origin, type-level diagnostics, how to tell it from its confusables, per-field provenance, and free-to-use images with licences. Thai and English.",
        "url": SITE_URL + "/", "license": DATA_LICENSE, "creator": AUTHOR, "inLanguage": ["th", "en"],
        "isAccessibleForFree": True, "keywords": ["Thai amulet", "พระเครื่อง", "เครื่องราง", "phra khrueang", "khrueang rang", "Buddhist amulet", "yantra", "takrut", "kuman thong", "hun payon"],
        "dateModified": max(r["updated"] for r in recs) if recs else time.strftime("%Y-%m-%d"),
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{SITE_URL}/api/kinds.json"},
            {"@type": "DataDownload", "encodingFormat": "application/x-ndjson", "contentUrl": f"{SITE_URL}/kinds.jsonl"},
            {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE_URL}/kinds.csv"},
        ],
        "variableMeasured": ["class", "resident", "upkeep", "provenance_sensitivity", "material", "function", "form", "region", "listings", "median_thb"],
    }
    ts = {"@context": "https://schema.org", "@type": "DefinedTermSet", "@id": f"{SITE_URL}/#termset", "name": SITE_NAME_EN,
          "hasDefinedTerm": [{"@type": "DefinedTerm", "@id": f"{SITE_URL}/kind/{r['id']}/", "name": r["names"]["th"], "alternateName": r["names"]["en"], "termCode": r["id"]} for r in recs]}
    return [ds, ts]


# ------------------------------------------------------------------ pages

def kind_page(rec: dict, by_id: dict, sources: dict) -> str:
    n = rec["names"]
    cf = rec["class_facts"]
    d = 2
    al = n.get("aliases") or {}
    prim = rec.get("primary_image")
    parts = [f'<nav class="crumbs"><a href="../../index.html">Directory</a> › {E(cf.get("term") or "ยังไม่ชี้ขาด")}</nav>']
    parts.append(f'<h1><span class="th">{E(n["th"])}</span> <span class="roman">{E(n["roman"])} · {E(n["en"])}</span></h1>')
    osc = n.get("other_scripts") or {}
    if osc:
        parts.append('<p class="lede">' + " · ".join(f'<span lang="{E(k)}">{E(v)}</span> <span class="mute">({E(k)})</span>' for k, v in osc.items()) + "</p>")
    aliases = f'<p class="mute" style="font-size:.9rem">also: {E(" · ".join(al.get("th", []) + al.get("roman", []) + al.get("en", [])))}</p>' if any(al.values()) else ""
    if rec.get("level") != "kind" and rec.get("parent") in by_id:
        p = by_id[rec["parent"]]
        parts.append(f'<p>{E(rec["level"])} of <a href="../{E(p["id"])}/index.html">{E(p["names"]["th"])} · {E(p["names"]["en"])}</a></p>')
    if prim:
        parts.append(img_tag(prim, rec, d, lazy=False, n=rec.get("images", []).index(prim) + 1))
    parts.append(cta(rec, 2))
    parts.append(f'<p class="lede th" lang="th">{E(rec["text"].get("what_th", ""))}</p><p class="lede" lang="en">{E(rec["text"]["what_en"])}</p>')
    parts.append(aliases)

    # at a glance
    rows = [
        ("Class · หมวด", f'{E(cf.get("term") or "ยังไม่ชี้ขาด")} <span class="mute">{E(cf.get("en_gloss") or cf.get("en") or "")}</span> {tier_chip(field_tier(rec, "axes").get("tier"), field_tier(rec, "axes").get("source", ""))}'),
        ("Resident · ผู้อยู่", E(cf.get("resident") or "left to a knower")),
        ("Upkeep · การเลี้ยง", E(cf.get("upkeep") or "left to a knower")),
        ("Provenance sensitivity", E(cf.get("provenance_sensitivity") or "—")),
        ("Form · รูปแบบ", f'{E(rec["form"]["type"])} · {E(FORM_TH.get(rec["form"]["type"], ""))}'),
        ("Material · เนื้อ", " · ".join(f'<a href="../../vocab/index.html#mat-{E(t["key"])}">{E(t["term"])}</a> <span class="mute">{E(t["en"])}</span>' for t in rec["material_terms"]) or "—"),
        ("Function · คุณ", " · ".join(f'<a href="../../vocab/index.html#fn-{E(t["key"])}">{E(t["term"])}</a> <span class="mute">{E(t["en"])}</span>' for t in rec["function_terms"]) or "—"),
        ("Region · ถิ่น", " · ".join(f'{E(t.get("th",""))} <span class="mute">{E(t.get("en",""))}</span>' for t in rec["region_terms"])),
    ]
    o = rec.get("origin") or {}
    if o.get("wat_th") or o.get("wat_en"):
        w = f'{E(o.get("wat_th",""))} <span class="mute">{E(o.get("wat_en",""))}</span>'
        if o.get("wat_url"):
            w = f'<a href="{E(o["wat_url"])}">{w}</a>'
        rows.append(("Temple · วัด", w))
    if o.get("maker_th") or o.get("maker_en"):
        rows.append(("Maker · ผู้สร้าง", f'{E(o.get("maker_th",""))} <span class="mute">{E(o.get("maker_en",""))}</span>'))
    if o.get("era_th") or o.get("era_en"):
        rows.append(("Era · ยุค", f'{E(o.get("era_th",""))} <span class="mute">{E(o.get("era_en",""))}</span> {tier_chip(field_tier(rec, "origin").get("tier"), field_tier(rec, "origin").get("source", ""))}'))
    f = rec["form"]
    if f.get("size_mm"):
        s = f["size_mm"]
        rows.append(("Typical size", f'{E(" × ".join(str(x) for x in s if x is not None))} mm {tier_chip(field_tier(rec, "form.size_mm").get("tier"))}'))
    ms = rec.get("market_stats")
    if ms and ms.get("listings"):
        typ = ms.get("typical_thb") or [None, None]
        med = f'median ฿{ms["median_thb"]:,.0f}' if ms.get("median_thb") else ""
        rng = f'฿{typ[0]:,.0f}–{typ[1]:,.0f} typical' if typ[0] is not None else ""
        rows.append(("Retail market (Lazada TH titles)", f'{ms["listings"]:,} listings · {rng} · {med} {tier_chip("catalogue", "s:catalog-db")}'))
    elif ms:
        rows.append(("Retail market (Lazada TH titles)", f'no listing title carries this term {tier_chip("catalogue", "s:catalog-db")}'))
    parts.append("<h2>At a glance · โดยย่อ</h2><table>" + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</table>")

    # form
    fr = []
    for k, lab in (("shape", "Shape · ทรง"), ("wearable", "Worn · การพก"), ("obverse", "Obverse · ด้านหน้า"), ("reverse", "Reverse · ด้านหลัง")):
        th, en = f.get(f"{k}_th", ""), f.get(f"{k}_en", "")
        if th or en:
            fr.append(f'<tr><th>{lab}</th><td><span class="th" lang="th">{E(th)}</span><br><span lang="en">{E(en)}</span></td></tr>')
    if f.get("notes_en"):
        fr.append(f'<tr><th>Notes</th><td>{E(f["notes_en"])}</td></tr>')
    if rec.get("iconography"):
        fr.append('<tr><th>Iconography · สัญลักษณ์</th><td>' + "<br>".join(f'<span class="th">{E(i.get("th",""))}</span> <span class="mute">{E(i.get("en",""))}</span>' for i in rec["iconography"]) + "</td></tr>")
    if fr:
        parts.append(f'<h2>Form · รูปทรง {tier_chip(field_tier(rec, "form").get("tier"), field_tier(rec, "form").get("source", ""))}</h2><table>{"".join(fr)}</table>')

    # diagnostics
    if rec.get("diagnostics"):
        parts.append("<h2>What to look at · จุดสังเกต</h2><p class=\"mute\">Type-level marks a reader can check by eye or loupe.</p><table>")
        for dg in rec["diagnostics"]:
            parts.append(f'<tr><td><span class="th" lang="th">{E(dg.get("th",""))}</span><br><span lang="en">{E(dg["en"])}</span></td><td style="width:30%">{tier_chip(dg.get("tier",""), dg.get("source",""))}</td></tr>')
        parts.append("</table>")

    # confusables
    if rec.get("confusable_with"):
        parts.append("<h2>How to tell it from · แยกจาก</h2><table>")
        for c in rec["confusable_with"]:
            oth = by_id.get(c["id"])
            name = f'<a href="../{E(c["id"])}/index.html">{E(oth["names"]["th"])} · {E(oth["names"]["en"])}</a>' if oth else E(c["id"])
            parts.append(f'<tr><th>{name}</th><td><span class="th" lang="th">{E(c.get("tell_th",""))}</span><br><span lang="en">{E(c["tell_en"])}</span></td></tr>')
        parts.append("</table>")

    # story + keeping
    t = rec["text"]
    if t.get("story_th") or t.get("story_en"):
        parts.append(f'<h2>The story · เรื่องเล่า {tier_chip(field_tier(rec, "text.story_en").get("tier"), field_tier(rec, "text.story_en").get("source", ""))}</h2>')
        if t.get("story_th"):
            parts.append(f'<p class="th" lang="th">{E(t["story_th"])}</p>')
        if t.get("story_en"):
            parts.append(f'<p lang="en">{E(t["story_en"])}</p>')
    if t.get("keeping_th") or t.get("keeping_en"):
        parts.append(f'<h2>Keeping · การเลี้ยงดู {tier_chip(field_tier(rec, "text.keeping_en").get("tier"), field_tier(rec, "text.keeping_en").get("source", ""))}</h2>')
        parts.append(f'<p class="th" lang="th">{E(t.get("keeping_th",""))}</p><p lang="en">{E(t.get("keeping_en",""))}</p>')

    # gallery
    others = [im for im in rec.get("images", []) if im is not prim]
    if others:
        parts.append('<h2>Pictures · ภาพ</h2><div class="gallery">' + "".join(img_tag(im, rec, d, n=i + 1) for i, im in enumerate(rec.get("images", [])) if im is not prim) + "</div>")
    elif not prim:
        want = (rec.get("media") or {}).get("wanted_en", "")
        parts.append(f'<h2>Pictures · ภาพ</h2><p class="mute">No free-to-use photograph yet. {E(want)}</p>')

    # sources + provenance
    parts.append("<h2>Sources · แหล่งที่มา</h2><ul>")
    for s in rec.get("sources", []):
        src = sources.get(s)
        if not src:
            continue
        link = f'<a href="{E(src["url"])}" rel="noopener">{E(src["title"])}</a>' if src.get("url") else E(src["title"])
        parts.append(f'<li>{link} <span class="mute">({E(src.get("type",""))}{"; " + E(src["license"]) if src.get("license") else ""})</span></li>')
    parts.append("</ul>")
    pv = rec.get("provenance", {})
    parts.append(f'<p class="legend">Default provenance: {tier_chip(pv.get("default", {}).get("tier"), pv.get("default", {}).get("source", ""))} '
                 + " ".join(f'{E(k)} → {tier_chip(v.get("tier"), v.get("source", ""))}' for k, v in (pv.get("fields") or {}).items())
                 + f' · confidence {E(rec["confidence"])}{" · needs verification" if rec.get("needs_verification") else ""} · updated {E(rec["updated"])}</p>')
    parts.append(f'<p class="bots">This record as data: <a href="../../api/kind/{E(rec["id"])}.json" type="application/json">JSON</a> · <a href="../../schema/kind.schema.json">schema</a></p>')
    canonical = f"{SITE_URL}/kind/{rec['id']}/"
    extra = f'<link rel="alternate" type="application/json" href="../../api/kind/{E(rec["id"])}.json">'
    card = CARDS_DIR / f"amulets__kind__{rec['id']}.png" if CARDS_DIR else None
    if card and card.exists():
        extra += f'<meta property="og:image" content="{E(SITE_URL)}/kind/{E(rec["id"])}/card.png"><meta name="twitter:card" content="summary_large_image">'
    elif prim:
        extra += f'<meta property="og:image" content="{E(img_abs(prim))}">'
    return page(f'{n["th"]} · {n["en"]} — {SITE_NAME_EN}', "\n".join(parts), d, rec["text"]["what_en"], kind_jsonld(rec, sources), canonical, extra)


def directory_page(recs: list[dict], vocab: dict) -> str:
    classes = vocab["classes"]
    order = list(classes.keys()) + [None]
    groups: dict = {k: [] for k in order}
    for r in recs:
        groups.setdefault(r["axes"].get("class"), []).append(r)
    total_img = sum(len(r.get("images", [])) for r in recs)
    parts = [f'<h1><span class="th">{SITE_NAME_TH}</span> <span class="roman">{SITE_NAME_EN} · the kinds of sacred object, as data</span></h1>',
             f'<p class="lede">{len(recs)} kinds · {total_img} free-to-use pictures · Thai and English · every field says where it came from. '
             f'Start from the class — <em>is anyone home?</em> — because that is the one fact a sale listing never states.</p>',
             '<form class="search" action="search/index.html" method="get" role="search"><input type="search" name="q" placeholder="ค้นหา · search: ตะกรุด, takrut, something that guards a house…" aria-label="Search"><button type="submit">Search</button></form>',
             '<div class="dir">']
    for key in order:
        rs = sorted(groups.get(key, []), key=lambda r: r["names"]["roman"])
        if not rs:
            continue
        c = classes.get(key) or {}
        head = f'{E(c.get("term") or "ยังไม่ชี้ขาด")} <span class="mute">{E(c.get("en_gloss") or "left to a knower")}</span> <span class="count">({len(rs)})</span>'
        sub = f'<p class="mute" style="font-size:.85rem;margin:.1rem 0 .3rem">resident: {E(c.get("resident") or "—")} · upkeep: {E(c.get("upkeep") or "—")}</p>' if c else '<p class="mute" style="font-size:.85rem;margin:.1rem 0 .3rem">the vocabulary declines to place these; the refusal is recorded</p>'
        items = "".join(
            f'<li><a href="kind/{E(r["id"])}/index.html"><span class="th">{E(r["names"]["th"])}</span></a> <span class="mute">{E(r["names"]["en"])}</span>'
            + (f' <span class="count">({r["market_stats"]["listings"]:,} listing{"s" if r["market_stats"]["listings"] != 1 else ""})</span>' if (r.get("market_stats") or {}).get("listings") else "")
            + ("" if r.get("images") else ' <span class="count" title="no free picture yet">◌</span>') + "</li>" for r in rs)
        parts.append(f'<section><h2>{head}</h2>{sub}<ul>{items}</ul></section>')
    parts.append("</div>")
    # second axis: by form, by region
    by_form: dict = {}
    for r in recs:
        by_form.setdefault(r["form"]["type"], []).append(r)
    parts.append('<h2>By form · ตามรูปแบบ</h2><div class="dir">')
    for ft, rs in sorted(by_form.items(), key=lambda kv: -len(kv[1])):
        parts.append(f'<section><h2>{E(ft)} <span class="mute">{E(FORM_TH.get(ft, ""))}</span> <span class="count">({len(rs)})</span></h2><ul>'
                     + "".join(f'<li><a href="kind/{E(r["id"])}/index.html">{E(r["names"]["th"])}</a> <span class="mute">{E(r["names"]["en"])}</span></li>' for r in sorted(rs, key=lambda r: r["names"]["roman"])) + "</ul></section>")
    parts.append("</div>")
    by_reg: dict = {}
    for r in recs:
        for rg in r["region"]:
            by_reg.setdefault(rg, []).append(r)
    regions = vocab["regions"]
    parts.append('<h2>By region · ตามถิ่น</h2><div class="dir">')
    for rg, rs in sorted(by_reg.items(), key=lambda kv: -len(kv[1])):
        e = regions.get(rg) or {"th": rg, "en": rg}
        parts.append(f'<section><h2>{E(e["th"])} <span class="mute">{E(e["en"])}</span> <span class="count">({len(rs)})</span></h2><ul>'
                     + "".join(f'<li><a href="kind/{E(r["id"])}/index.html">{E(r["names"]["th"])}</a> <span class="mute">{E(r["names"]["en"])}</span></li>' for r in sorted(rs, key=lambda r: r["names"]["roman"])) + "</ul></section>")
    empty = [e for k, e in regions.items() if k not in by_reg]
    if empty:
        parts.append(f'<section><h2>Slots with no records yet <span class="count">({len(empty)})</span></h2><p class="mute" style="font-size:.85rem">{E(" · ".join(e["en"] for e in empty))}</p></section>')
    parts.append("</div>")
    parts.append('<p class="legend"><b>Boundary · ขอบเขต:</b> this catalogue holds no ivory, no tiger parts, and no necromantic objects beyond กุมารทอง, which is described ethnographically. They are not catalogued, not sold through the register, and not discussed here.</p>')
    parts.append('<p class="legend">◌ = no free-to-use picture yet. Counts in parentheses are Lazada Thailand listing titles carrying the term (delete-then-test exclusions applied). Provenance tiers: '
                 + " ".join(tier_chip(t) for t in ("catalogue", "cited", "tradition", "inference", "field")) + "</p>")
    extra = f'<meta property="og:image" content="{E(SITE_URL)}/card.png"><meta name="twitter:card" content="summary_large_image">' if (CARDS_DIR and (CARDS_DIR / "amulets.png").exists()) else ""
    return page(f"{SITE_NAME_EN} · {SITE_NAME_TH}", "\n".join(parts), 0,
                "Structured, bilingual catalogue of the kinds of Thai and Southeast Asian amulet: class, material, function, form, origin, diagnostics, confusables, provenance, free images.",
                index_jsonld(recs), SITE_URL + "/", extra)


def vocab_page(vocab: dict) -> str:
    parts = ['<h1>Vocabulary · คำศัพท์ <span class="roman">the three axes every record hangs on, from the wichaa vault</span></h1>']
    for axis, prefix, title in (("classes", "cls", "Class · หมวด — is anyone home?"), ("materials", "mat", "Material · เนื้อ — the first thing a sian names"), ("functions", "fn", "Function · คุณ — what it is for")):
        parts.append(f"<h2>{E(title)}</h2><table>")
        for k, e in vocab[axis].items():
            extra = ""
            if axis == "classes":
                extra = f'<br><span class="mute">resident {E(e.get("resident",""))} · upkeep {E(e.get("upkeep",""))} · provenance {E(e.get("provenance_sensitivity",""))}</span>'
            elif axis == "materials":
                extra = f'<br><span class="mute">family {E(e.get("family",""))} · dating signal {E(e.get("dating_signal",""))} · counterfeit pressure {E(e.get("counterfeit_pressure",""))}</span>'
            parts.append(f'<tr id="{prefix}-{E(k)}"><th><span class="th">{E(e.get("term",""))}</span><br><span class="mute">{E(e.get("roman",""))} · {E(e.get("en_gloss",""))}</span></th><td>{E(e.get("definition",""))}{extra}</td></tr>')
        parts.append("</table>")
    parts.append('<h2>Regions · ถิ่น <span class="mute">(open list)</span></h2><ul>' + "".join(f'<li><span class="th">{E(e["th"])}</span> · {E(e["en"])} <span class="count">({E(k)})</span></li>' for k, e in vocab["regions"].items()) + "</ul>")
    ld = [{"@context": "https://schema.org", "@type": "DefinedTermSet", "name": f"{SITE_NAME_EN} vocabulary — {axis}",
           "hasDefinedTerm": [{"@type": "DefinedTerm", "name": e.get("term", ""), "alternateName": e.get("en_gloss", ""), "description": e.get("definition", ""), "termCode": k} for k, e in vocab[axis].items()]}
          for axis in ("classes", "materials", "functions")]
    return page(f"Vocabulary — {SITE_NAME_EN}", "\n".join(parts), 1, "Class, material and function vocabularies behind the amulet records, with definitions.", ld, f"{SITE_URL}/vocab/")


def sources_page(sources: dict) -> str:
    parts = ['<h1>Sources · แหล่งที่มา</h1><p class="mute">Every record cites ids from this registry. Wikipedia text is cited, not copied. web-pra and uamulet are linked never ingested, at their own request.</p><table>']
    for s in sources.values():
        link = f'<a href="{E(s["url"])}" rel="noopener">{E(s["title"])}</a>' if s.get("url") else E(s["title"])
        parts.append(f'<tr><th><code>{E(s["id"])}</code><br><span class="mute">{E(s.get("type",""))}</span></th><td>{link}<br><span class="mute">{E(s.get("license",""))}{" · " + E(s["note"]) if s.get("note") else ""}</span></td></tr>')
    parts.append("</table>")
    return page(f"Sources — {SITE_NAME_EN}", "\n".join(parts), 1, "Source registry for the amulet records.", None, f"{SITE_URL}/sources/")


def search_page(recs: list[dict]) -> str:
    docs = []
    for r in recs:
        n = r["names"]
        al = n.get("aliases") or {}
        docs.append({
            "id": r["id"], "level": r.get("level", "kind"), "th": n["th"], "en": n["en"], "roman": n["roman"], "cls": r["class_facts"].get("term") or "",
            "what_th": r["text"].get("what_th", ""), "what_en": r["text"]["what_en"], "img": img_src(r["primary_image"], 1) if r.get("primary_image") else None,
            "name": " ".join([n["th"], n["roman"], n["en"]] + list((n.get("other_scripts") or {}).values()) + al.get("th", []) + al.get("roman", []) + al.get("en", [])),
            "terms": " ".join([r["class_facts"].get("term") or "", r["class_facts"].get("en_gloss") or ""] + [f"{t['term']} {t['en']}" for t in r["function_terms"] + r["material_terms"]] + [f"{t.get('th','')} {t.get('en','')}" for t in r["region_terms"]]),
            "text": " ".join([r["text"].get("what_th", ""), r["text"]["what_en"], r["text"].get("story_en", ""), r["text"].get("keeping_en", "")] + [f"{i.get('th','')} {i.get('en','')}" for i in r.get("iconography", [])] + [f"{x.get('th','')} {x.get('en','')}" for x in r.get("diagnostics", [])]),
        })
    body = f"""
<h1>Search · ค้นหา <span class="roman">Thai or English, spelled however you spell it</span></h1>
<form class="search" role="search" onsubmit="return false"><input id="q" type="search" placeholder="ตะกรุด · takrut · something that guards a house and is fed…" aria-label="Search" autofocus><button id="go" type="button">Search</button></form>
<p id="tier" class="tierline" aria-live="polite"></p>
<div id="out" class="cards"></div>
<p class="legend" id="how">Lexical search runs in your browser: exact → same meaning, other word → near spellings → partial. When this page is served by tools/serve.py, results by <em>meaning</em> (vectors) are fused in and marked.</p>
<script src="../vendor/searchcore.js"></script>
<script>
(function(){{
var DOCS={json.dumps(docs, ensure_ascii=False)};
var TABLES=null, core=null, index=null, PREP=null;
var byId={{}}; DOCS.forEach(function(d){{byId[d.id]=d}});
var TIER_TH={{exact:"ตรงคำ",thesaurus:"คำพ้อง",loose:"ใกล้เคียง",partial:"บางส่วน",meaning:"ตามความหมาย"}};
var TIER_EN={{exact:"exact match",thesaurus:"same meaning, other word",loose:"near spellings — closest first",partial:"partial matches",meaning:"by meaning"}};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
function build(){{
  core=new SEARCHCORE.SearchCore(TABLES.groups||[],TABLES.words||[]);
  index=new SEARCHCORE.Index(core);
  PREP={{}};
  DOCS.forEach(function(d){{var f={{name:[d.name,3],terms:[d.terms,2],text:[d.text,1]}};index.add(d,f);PREP[d.id]=core.prepareDoc(f)}});
  index.finalize();
}}
function card(d,tier,extra){{
  var img=d.img?'<img src="'+esc(d.img)+'" alt="" loading="lazy" style="width:100%;border-radius:8px;margin-bottom:.4rem">':'';
  return '<div class="card">'+img+'<a class="t" href="../kind/'+esc(d.id)+'/index.html"><span class="th">'+esc(d.th)+'</span> · '+esc(d.en)+'</a><p>'+esc(d.cls)+'</p><p lang="th" class="th">'+esc(d.what_th)+'</p><p lang="en">'+esc(d.what_en)+'</p><p><span class="chip">'+esc(TIER_EN[tier]||tier)+' · '+esc(TIER_TH[tier]||"")+'</span>'+(extra||'')+'</p></div>';
}}
function lexical(q){{
  /* the Index is the mending oracle; scoring is per document (fleet rule for small corpora,
     and the only way a two-word name like "kuman thong" matches at the exact tier) */
  var an=core.analyze(q,index); var rows=[];
  for(var id in PREP){{var r=core.scoreDoc(an,PREP[id]); if(r) rows.push({{id:id,tier:r.tier,score:r.score*(byId[id]&&byId[id].level==="kind"?1:0.95),coverage:r.coverage}})}}
  var whole=rows.filter(function(r){{return r.coverage>=1}}); var kept=whole.length?whole:rows;
  kept.sort(function(a,b){{return b.score-a.score}}); return kept.slice(0,24);
}}
function render(rows,worst,note){{
  var out=document.getElementById("out"), t=document.getElementById("tier");
  if(!rows.length){{out.innerHTML="";t.textContent="Nothing in the catalogue answers to that yet · ยังไม่มีในสารบบ";return}}
  t.textContent=(TIER_EN[worst]||worst)+" · "+(TIER_TH[worst]||"")+(note?" · "+note:"");
  out.innerHTML=rows.map(function(r){{var d=byId[r.id];return d?card(d,r.tier,r.meaning!=null?' <span class="chip">meaning '+r.meaning.toFixed(2)+'</span>':''):''}}).join("");
}}
var ctrl=null;
function run(){{
  var q=document.getElementById("q").value.trim(); if(!q){{render([],null);return}}
  var lex=lexical(q); var worst=null;
  lex.forEach(function(r){{if(worst==null||SEARCHCORE.TIER_ORDER.indexOf(r.tier)>SEARCHCORE.TIER_ORDER.indexOf(worst))worst=r.tier}});
  render(lex,worst||"exact");
  if(ctrl)ctrl.abort(); ctrl=new AbortController();
  fetch("/api/search?q="+encodeURIComponent(q)+"&n=24",{{signal:ctrl.signal}}).then(function(r){{return r.ok?r.json():null}}).then(function(j){{
    if(!j||!j.results)return; if(!j.meaning_available)return;
    render(j.results.map(function(r){{return {{id:r.id,tier:r.tier,meaning:r.meaning}}}}),j.worst_tier||"meaning","with meaning search");
  }}).catch(function(){{}});
}}
fetch("tables.json").then(function(r){{return r.json()}}).then(function(t){{TABLES=t;build();
  var u=new URL(location.href); var q0=u.searchParams.get("q"); if(q0){{document.getElementById("q").value=q0;run()}}
}});
document.getElementById("go").addEventListener("click",run);
document.getElementById("q").addEventListener("keydown",function(e){{if(e.key==="Enter"&&!e.isComposing){{e.preventDefault();run()}}}});
document.getElementById("q").addEventListener("input",function(){{if(index)run()}});
}})();
</script>
"""
    return page(f"Search — {SITE_NAME_EN}", body, 1, "Search the amulet catalogue in Thai or English; misspellings and compounds understood.", None, f"{SITE_URL}/search/")


def identify_page(sha_map: dict) -> str:
    """The recogniser runs on the reader's device (tools/identify.js). This page is the
    intake and the review: camera OR gallery (many at once), drag-drop and paste on a
    desktop, photos shared into the installed app, a day's haul kept in IndexedDB with
    corrections and a copyable summary. A ?kind= arrival (from a kind or picture page)
    frames every result against that kind."""
    js = (Path(__file__).resolve().parent / "identify.js").read_text(encoding="utf-8")
    body = f"""
<h1>ส่องภาพ · Photograph it <span class="roman">ชนิดไหน? · which kind does this look like?</span></h1>
<div id="frame" class="card" hidden><p><b>เทียบกับ · comparing against</b> <span id="framekind"></span> — every result below says where that kind ranked. <a href="index.html">Clear</a></p></div>
<div id="drop" class="drop">
  <label class="big" for="pick">🖼 <span class="th">เลือกรูปจากเครื่อง</span><br><span>Choose photos · many at once</span><input id="pick" type="file" accept="image/*" multiple></label>
  <label class="big" for="snap">📷 <span class="th">ถ่ายรูปตอนนี้</span><br><span>Take a photo</span><input id="snap" type="file" accept="image/*" capture="environment"></label>
  <p class="mute">or drop pictures here · or paste one · or Share from your gallery to the installed app</p>
</div>
<p id="status" class="tierline" aria-live="polite">…</p>
<progress id="bar" max="100" hidden></progress>
<p class="mute" lang="th">เลือกได้หลายรูป · เทียบในเครื่องคุณเอง รูปไม่ถูกส่งไปไหน · ตอบเป็น<em>ชนิด</em> ไม่ใช่แท้หรือไม่แท้</p>
<p class="mute" lang="en">Many at once, compared on your own device · answers with the <em>kind</em>.</p>
<section id="haul" hidden>
  <h2 id="haulhead"></h2>
  <ul id="haullist" class="dirlist"></ul>
  <p><button id="copy" type="button" class="ghost">📋 คัดลอกสรุป · copy summary</button> <button id="share" type="button" class="ghost">↗ แชร์ · share</button> <button id="clear" type="button" class="ghost">🗑 ล้างทั้งหมด · clear all</button></p>
</section>
<div id="shots" class="shots"></div>
<p class="legend">Photos and results stay in this browser only (IndexedDB), until you clear them. The recogniser (CLIP ViT-B/32, about 22 MB) downloads once and is cached; after that this page works offline. Install the site (Add to Home Screen) and it appears in your phone's Share sheet. Resemblance is to the catalogue's reference pictures.</p>
<script>window.IDENT={json.dumps({"imgBase": IMAGE_BASE, "siteUrl": SITE_URL})};(function(){{var u=new URL(location.href);var k=u.searchParams.get("kind");if(k)window.IDENT.kind=k;}})();</script>
<script>{js}</script>
"""
    css = """
.drop{border:2px dashed var(--line);border-radius:14px;padding:1rem;display:flex;gap:1rem;flex-wrap:wrap;align-items:stretch;background:var(--card);margin:.8rem 0}.drop.over{border-color:var(--teal)}
.drop .big{flex:1 1 14rem;min-height:6rem;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:.2rem;border:2px solid var(--teal);border-radius:12px;padding:1rem;font-size:1.15rem;cursor:pointer;background:var(--bg)}.drop .big input{position:absolute;width:1px;height:1px;opacity:0}.drop .big:focus-within{outline:3px solid var(--focus);outline-offset:2px}.drop .big .th{font-size:1.3rem;font-weight:700}.drop p{flex-basis:100%;margin:.2rem 0 0;font-size:.9rem}
progress{width:100%;height:.8rem;margin:.2rem 0 .8rem}
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:1rem;margin-top:1rem}.shot{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.7rem;display:flex;flex-direction:column;gap:.4rem}.shot img{width:100%;height:auto;border-radius:8px;display:block;aspect-ratio:1;object-fit:cover}.shot .t{font-weight:700;text-decoration:none;font-size:1.1rem}.shot p{margin:.15rem 0}.shot ol{padding-left:1.2rem;margin:.3rem 0}.shot .fix{display:block;font-size:.85rem;color:var(--mute);margin-top:.3rem}.shot .fix select{width:100%;font:inherit;font-size:.95rem;margin-top:.2rem;padding:.3rem;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
.near{display:grid;grid-template-columns:repeat(6,1fr);gap:.3rem;margin:.4rem 0}.near img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;display:block}
button.ghost{font:inherit;padding:.5rem .9rem;border-radius:10px;border:2px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font-size:.95rem}button.ghost:hover{border-color:var(--teal)}.shot .del{align-self:flex-end;font-size:.8rem;padding:.25rem .6rem}
.band-strong{border-color:var(--teal)}.band-likely{border-color:var(--gold)}.band-weak{border-style:dashed}.band-text{border-style:dotted}.band-corrected{border-color:var(--focus)}
.dirlist{list-style:none;padding:0;margin:.3rem 0}.dirlist li{margin:.15rem 0}
@media (prefers-reduced-motion: no-preference){.drop .big{transition:transform .15s}.drop .big:hover{transform:translateY(-2px)}}
"""
    return page(f"Photograph it — {SITE_NAME_EN}", body, 1,
                "Photograph an amulet, or choose many from your gallery, and see which kinds each resembles, on your own device.",
                [{"@context": "https://schema.org", "@type": "WebApplication", "name": "Photograph it · ส่องภาพ", "applicationCategory": "UtilitiesApplication",
                  "operatingSystem": "Any", "browserRequirements": "Requires JavaScript; works offline after first use", "url": f"{SITE_URL}/identify/",
                  "description": "On-device reverse-image identification of the KIND of Thai and Southeast Asian amulet, against free-licensed reference pictures.", "isAccessibleForFree": True}],
                f"{SITE_URL}/identify/", f"<style>{css}</style>")


def manifest() -> str:
    return json.dumps({
        "name": f"{SITE_NAME_EN} · {SITE_NAME_TH}", "short_name": "Amulets", "start_url": "./identify/index.html?source=pwa",
        "scope": "./", "display": "standalone", "background_color": "#fbf8f2", "theme_color": "#1f6f6b", "lang": "th",
        "description": "Photograph an amulet; see which kind it resembles, with its record in Thai and English.",
        "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
        "share_target": {"action": "./identify/share", "method": "POST", "enctype": "multipart/form-data",
                         "params": {"title": "title", "text": "text", "url": "url", "files": [{"name": "photo", "accept": ["image/*"]}]}},
    }, ensure_ascii=False, indent=1)


def sw_js() -> str:
    # Two jobs. (1) Receive photos shared into the installed app (Web Share Target): park
    # every file in the cache and send the reader to /identify/, which drains it. (2) Keep the
    # identify page and its bank available offline — a sian in a market stall has no signal.
    # The recogniser model is cached by transformers.js itself (browser Cache API). Pages
    # elsewhere on the site are NOT cached, so a republish is never stale; the cache name
    # carries the build date so a new build replaces the old assets on next load.
    return """var CACHE='amulet-identify-""" + time.strftime("%Y%m%d%H%M") + """';
var ASSETS=['./identify/index.html','./identify/bank.json','./vendor/searchcore.js','./manifest.webmanifest','./icon.svg'];
self.addEventListener('install',function(e){e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(ASSETS).catch(function(){})}).then(function(){return self.skipWaiting()}))});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.filter(function(k){return k.indexOf('amulet-identify-')===0&&k!==CACHE}).map(function(k){return caches.delete(k)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener('fetch',function(e){
  var u=new URL(e.request.url);
  if(e.request.method==='POST'&&u.pathname.endsWith('/identify/share')){
    e.respondWith((async function(){
      try{var fd=await e.request.formData();var files=fd.getAll('photo');var c=await caches.open('shared-photo');var i=0;
        for(var f of files){if(f&&f.size){await c.put('/identify/shared-'+Date.now()+'-'+(i++),new Response(f,{headers:{'Content-Type':f.type||'image/jpeg'}}))}}
      }catch(err){}
      return Response.redirect(u.pathname.replace(/share$/,'index.html?shared=1'),303);
    })());
    return;
  }
  if(e.request.method!=='GET')return;
  var p=u.pathname;
  if(p.indexOf('/identify/')>=0||p.endsWith('/vendor/searchcore.js')||p.endsWith('/manifest.webmanifest')||p.endsWith('/icon.svg')){
    // network first, cache fallback: fresh when online, working when not
    e.respondWith(fetch(e.request).then(function(r){var cp=r.clone();caches.open(CACHE).then(function(c){c.put(e.request,cp)});return r}).catch(function(){return caches.match(e.request)}));
  }
});
"""


def icon_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1f6f6b"/>'
            '<path d="M32 10c-9 0-15 8-15 20 0 11 6 20 15 24 9-4 15-13 15-24 0-12-6-20-15-20z" fill="#fbf8f2"/>'
            '<circle cx="32" cy="30" r="7" fill="#1f6f6b"/><path d="M22 46c3-5 17-5 20 0" stroke="#1f6f6b" stroke-width="3" fill="none" stroke-linecap="round"/></svg>')


# ------------------------------------------------------------------ bot files

def llms_txt(recs: list[dict]) -> str:
    lines = [f"# {SITE_NAME_EN} · {SITE_NAME_TH}", "",
             "> Structured, bilingual (Thai/English) catalogue of the KINDS of Thai and Southeast Asian sacred object — amulets and charms (พระเครื่อง / เครื่องราง). One record per kind: emic term, romanisation, English gloss, class (does anything live in it; what the keeper owes it), material, function, form, origin, type-level diagnostics, how to tell it from its confusables, per-field provenance, free-to-use images with licences.",
             "", "Boundary: no ivory, no tiger parts, no necromantic objects beyond kuman thong (described ethnographically). Such items are not catalogued, not sold, not discussed.",
             "", f"Records are CC BY 4.0 ({DATA_LICENSE}). Images carry their own licences (CC0 / public domain / CC BY / CC BY-SA only), stated per file. The emic Thai term is the identity; English is a gloss. Every field carries a provenance tier: catalogue (checkable in the corpus), cited (named external source), tradition (general knowledge, hedged), inference, field.",
             "", "## Data", f"- [All kinds, JSON]({SITE_URL}/api/kinds.json)", f"- [Directory index, JSON]({SITE_URL}/api/index.json)",
             f"- [JSONL]({SITE_URL}/kinds.jsonl) · [CSV]({SITE_URL}/kinds.csv)", f"- [Record schema]({SITE_URL}/schema/kind.schema.json)",
             f"- [Vocabularies: class, material, function, region]({SITE_URL}/vocab/) · JSON under {SITE_URL}/api/vocab/",
             f"- [Sources registry]({SITE_URL}/api/sources.json)", f"- [Full text of every record]({SITE_URL}/llms-full.txt)", "", "## Kinds"]
    for r in sorted(recs, key=lambda r: r["names"]["roman"]):
        lines.append(f"- [{r['names']['th']} · {r['names']['en']}]({SITE_URL}/kind/{r['id']}/): {r['text']['what_en']}")
    lines += ["", "## Optional", f"- [Search page]({SITE_URL}/search/) — Thai/English, fuzzy, compound-aware", f"- [Photograph it]({SITE_URL}/identify/) — reverse-image identification of the kind", f"- [What sets the price]({SITE_URL}/value/) — the factors that assign cash value, ranked, with the market tiers; data at {SITE_URL}/api/value_factors.json", f"- [Atom feed]({SITE_URL}/feed.xml)", f"- [Sitemap]({SITE_URL}/sitemap.xml)"]
    return "\n".join(lines) + "\n"


def llms_full(recs: list[dict], sources: dict) -> str:
    out = [f"# {SITE_NAME_EN} — every record, flattened\n"]
    for r in sorted(recs, key=lambda r: r["names"]["roman"]):
        n = r["names"]
        cf = r["class_facts"]
        out.append(f"## {n['th']} · {n['roman']} · {n['en']}\nURL: {SITE_URL}/kind/{r['id']}/\nJSON: {SITE_URL}/api/kind/{r['id']}.json\nid: {r['id']} · level: {r['level']}" + (f" · parent: {r['parent']}" if r.get("parent") else ""))
        al = n.get("aliases") or {}
        if n.get("other_scripts"):
            out.append("native: " + " · ".join(f"{v} ({k})" for k, v in n["other_scripts"].items()))
        if any(al.values()):
            out.append("aliases: " + " · ".join(al.get("th", []) + al.get("roman", []) + al.get("en", [])))
        out.append(f"class: {cf.get('term') or 'unplaced'} ({cf.get('en_gloss') or 'left to a knower'}) · resident: {cf.get('resident')} · upkeep: {cf.get('upkeep')} · provenance sensitivity: {cf.get('provenance_sensitivity')}")
        out.append(f"form: {r['form']['type']} · materials: {', '.join(t['term'] + ' (' + t['en'] + ')' for t in r['material_terms']) or '—'} · functions: {', '.join(t['term'] + ' (' + t['en'] + ')' for t in r['function_terms']) or '—'} · region: {', '.join(r['region'])}")
        o = r.get("origin") or {}
        if any(o.get(k) for k in ("wat_th", "maker_th", "era_en", "place_en")):
            out.append(f"origin: {o.get('wat_th','')} {o.get('wat_en','')} · {o.get('maker_th','')} {o.get('maker_en','')} · {o.get('era_en','')} · {o.get('place_en','')}".replace("  ", " "))
        out.append(f"what (th): {r['text'].get('what_th','')}\nwhat (en): {r['text']['what_en']}")
        for k in ("story_en", "keeping_en"):
            if r["text"].get(k):
                out.append(f"{k[:-3]}: {r['text'][k]}")
        for dg in r.get("diagnostics", []):
            out.append(f"- look at: {dg['en']} [{dg.get('tier','')}]")
        for c in r.get("confusable_with", []):
            out.append(f"- vs {c['id']}: {c['tell_en']}")
        for im in r.get("images", []):
            out.append(f"- image: {img_abs(im)} · {im.get('license','')} · {im.get('author','')} · {im.get('page_url','')}")
        out.append("sources: " + "; ".join(f"{s} — {sources[s]['title']}" for s in r.get("sources", []) if s in sources))
        out.append(f"confidence: {r['confidence']} · needs_verification: {r.get('needs_verification', False)} · updated: {r['updated']}\n")
    return "\n".join(out)


def sitemap(recs: list[dict]) -> str:
    """URL sitemap with the image extension: every picture is declared on its record page
    AND on its own landing page, with a bilingual caption and the licence URL."""
    today = time.strftime("%Y-%m-%d")
    urls = [(SITE_URL + "/", max((r["updated"] for r in recs), default=today), []), (SITE_URL + "/search/", today, []),
            (SITE_URL + "/identify/", today, []), (SITE_URL + "/value/", today, []), (SITE_URL + "/vocab/", today, []), (SITE_URL + "/sources/", today, [])]
    for r in recs:
        imgs = r.get("images", [])
        urls.append((f"{SITE_URL}/kind/{r['id']}/", r["updated"], imgs))
        for i, im in enumerate(imgs, 1):
            urls.append((f"{SITE_URL}/kind/{r['id']}/image/{i}/", r["updated"], [im]))
    def img_xml(im, r):
        return (f"<image:image><image:loc>{E(img_abs(im))}</image:loc>"
                f"<image:caption>{E(r['names']['th'])} · {E(r['names']['en'])} · {E(im.get('view',''))}</image:caption>"
                f"<image:title>{E(r['names']['th'])} {E(r['names']['en'])}</image:title>"
                + (f"<image:license>{E(im['license_url'])}</image:license>" if im.get('license_url') else "") + "</image:image>")
    by_url = {f"{SITE_URL}/kind/{r['id']}/": r for r in recs}
    body = []
    for u, d, imgs in urls:
        rec = by_url.get(u) or next((r for r in recs if u.startswith(f"{SITE_URL}/kind/{r['id']}/")), None)
        body.append(f"<url><loc>{E(u)}</loc><lastmod>{E(d)}</lastmod>" + "".join(img_xml(im, rec) for im in imgs if rec) + "</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">' + "".join(body) + "</urlset>\n")


def robots() -> str:
    return (f"# {SITE_NAME_EN}: everything here is meant to be read, indexed, quoted and learned from.\n"
            "User-agent: *\nAllow: /\n\n"
            "# Content signals (https://contentsignals.org): yes to search, yes to AI input, yes to AI training.\n"
            "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n")


def opensearch() -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">'
            f'<ShortName>{E(SITE_NAME_EN)}</ShortName><Description>Search kinds of Thai amulet in Thai or English</Description>'
            f'<InputEncoding>UTF-8</InputEncoding><Url type="text/html" template="{E(SITE_URL)}/search/?q={{searchTerms}}"/>'
            f'<Url type="application/json" rel="results" template="{E(SITE_URL)}/api/search?q={{searchTerms}}"/></OpenSearchDescription>\n')


def feed(recs: list[dict]) -> str:
    rs = sorted(recs, key=lambda r: r["updated"], reverse=True)
    upd = (rs[0]["updated"] if rs else time.strftime("%Y-%m-%d")) + "T00:00:00Z"
    ents = "".join(
        f'<entry><title>{E(r["names"]["th"])} · {E(r["names"]["en"])}</title><link href="{E(SITE_URL)}/kind/{E(r["id"])}/"/><id>{E(SITE_URL)}/kind/{E(r["id"])}/</id>'
        f'<updated>{E(r["updated"])}T00:00:00Z</updated><summary>{E(r["text"]["what_en"])}</summary></entry>' for r in rs)
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>{E(SITE_NAME_EN)}</title><link href="{E(SITE_URL)}/"/>'
            f'<link rel="self" href="{E(SITE_URL)}/feed.xml"/><id>{E(SITE_URL)}/</id><updated>{upd}</updated><author><name>Nan Peacock</name></author>{ents}</feed>\n')


def dumps(recs: list[dict]):
    rows = []
    for r in recs:
        cf = r["class_facts"]
        ms = r.get("market_stats") or {}
        rows.append({
            "id": r["id"], "level": r["level"], "parent": r.get("parent") or "", "name_th": r["names"]["th"], "name_roman": r["names"]["roman"], "name_en": r["names"]["en"],
            "class": r["axes"].get("class") or "", "class_th": cf.get("term") or "", "resident": cf.get("resident") or "", "upkeep": cf.get("upkeep") or "",
            "provenance_sensitivity": cf.get("provenance_sensitivity") or "", "form": r["form"]["type"], "materials": "|".join(r["axes"].get("materials", [])),
            "functions": "|".join(r["axes"].get("functions", [])), "region": "|".join(r["region"]), "wat_th": (r.get("origin") or {}).get("wat_th", ""),
            "maker_th": (r.get("origin") or {}).get("maker_th", ""), "era_en": (r.get("origin") or {}).get("era_en", ""),
            "what_th": r["text"].get("what_th", ""), "what_en": r["text"]["what_en"], "listings": ms.get("listings", ""), "median_thb": ms.get("median_thb", ""),
            "image": (r.get("primary_image") or {}).get("file", ""), "image_license": (r.get("primary_image") or {}).get("license", ""),
            "url": f"{SITE_URL}/kind/{r['id']}/", "json": f"{SITE_URL}/api/kind/{r['id']}.json", "confidence": r["confidence"], "updated": r["updated"],
        })
    with open(SITE / "kinds.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)
    with open(SITE / "kinds.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_") and k != "tier_labels"}, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ main

def main() -> int:
    if not (API / "kinds.json").exists():
        raise SystemExit("build/api missing — run tools/build.py first")
    t0 = time.time()
    recs = jload(API / "kinds.json")["kinds"]
    by_id = {r["id"]: r for r in recs}
    sources = {s["id"]: s for s in jload(API / "sources.json")["sources"]}
    vocab = {a: {e["key"]: e for e in jload(API / "vocab" / f"{a}.json")["entries"]} for a in ("classes", "materials", "functions", "regions")}
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copytree(API, SITE / "api")
    shutil.copytree(DATA.parent / "schema", SITE / "schema")
    (SITE / "vendor").mkdir()
    shutil.copy(VENDOR / "searchcore.js", SITE / "vendor" / "searchcore.js")
    n_img = 0
    for r in recs:
        for im in r.get("images", []):
            src = IMAGES / im["file"]
            if IMAGE_BASE:
                n_img += 1
                continue
            if src.exists():
                dst = SITE / "images" / im["file"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
                n_img += 1
    (SITE / "index.html").write_text(directory_page(recs, vocab), encoding="utf-8")
    n_pages = 0
    for r in recs:
        d = SITE / "kind" / r["id"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(kind_page(r, by_id, sources), encoding="utf-8")
        for i, im in enumerate(r.get("images", []), 1):
            pd = d / "image" / str(i)
            pd.mkdir(parents=True)
            (pd / "index.html").write_text(image_page(r, im, i, sources, by_id), encoding="utf-8")
            n_pages += 1
    # /value — the price analysis, drawn from data/analysis/value_factors.json when it exists
    vf_path = DATA / "analysis" / "value_factors.json"
    if vf_path.exists():
        import value_page
        vf = jload(vf_path)
        ps_path = DATA / "analysis" / "price_stats.json"
        ps = jload(ps_path) if ps_path.exists() else None
        (SITE / "value").mkdir()
        (SITE / "value" / "index.html").write_text(
            page(f"What sets the price — {SITE_NAME_EN}", value_page.render(vf, ps), 1,
                 "How cash value is assigned to Thai and Southeast Asian amulets: the factors ranked, the market tiers, and what our corpus shows.",
                 [{"@context": "https://schema.org", "@type": "Article", "headline": "How cash value is assigned to amulets", "inLanguage": ["th", "en"], "author": AUTHOR, "license": DATA_LICENSE, "url": f"{SITE_URL}/value/"}],
                 f"{SITE_URL}/value/", f"<style>{value_page.VIZ_CSS}</style>"), encoding="utf-8")
        shutil.copy(vf_path, SITE / "api" / "value_factors.json")
        if ps:
            shutil.copy(ps_path, SITE / "api" / "price_stats.json")
    srcs = DATA / "analysis" / "image_sources.json"
    if srcs.exists():
        shutil.copy(srcs, SITE / "api" / "image_sources.json")
    (SITE / "identify").mkdir()
    sha_map = {im["file"]: f"{im.get('sha256','')}{Path(im['file']).suffix.lower()}" for r in recs for im in r.get("images", []) if im.get("sha256")}
    (SITE / "identify" / "index.html").write_text(identify_page(sha_map), encoding="utf-8")
    bank = BUILD / "bank_browser.json"
    if bank.exists():
        shutil.copy(bank, SITE / "identify" / "bank.json")
    else:
        print("site: ! build/bank_browser.json missing — /identify/ will report no bank (run: node tools/bank_browser.mjs)")
    (SITE / "manifest.webmanifest").write_text(manifest(), encoding="utf-8")
    (SITE / "sw.js").write_text(sw_js(), encoding="utf-8")
    (SITE / "icon.svg").write_text(icon_svg(), encoding="utf-8")
    (SITE / "vocab").mkdir()
    (SITE / "vocab" / "index.html").write_text(vocab_page(vocab), encoding="utf-8")
    (SITE / "sources").mkdir()
    (SITE / "sources" / "index.html").write_text(sources_page(sources), encoding="utf-8")
    (SITE / "search").mkdir()
    (SITE / "search" / "index.html").write_text(search_page(recs), encoding="utf-8")
    # search tables: fleet + wichaa + this project's mined tables, one file, fetched by the search page only
    groups, words = [], []
    from common import SEARCH_CORE
    for p in (SEARCH_CORE / "data" / "thesaurus.json", SEARCH_CORE / "data" / "wichaa.thesaurus.json", DATA / "search" / "amulets.thesaurus.json"):
        if p.exists():
            dd = jload(p)
            groups.extend(dd["groups"] if isinstance(dd, dict) else dd)
    for p in (SEARCH_CORE / "data" / "segdict.txt", SEARCH_CORE / "data" / "wichaa.segdict.txt", DATA / "search" / "amulets.segdict.txt"):
        if p.exists():
            words.extend(w for w in p.read_text(encoding="utf-8").split("\n") if w.strip() and not w.startswith("#"))
    (SITE / "search" / "tables.json").write_text(json.dumps({"groups": groups, "words": sorted(set(words))}, ensure_ascii=False), encoding="utf-8")
    (SITE / "llms.txt").write_text(llms_txt(recs), encoding="utf-8")
    (SITE / "llms-full.txt").write_text(llms_full(recs, sources), encoding="utf-8")
    (SITE / "sitemap.xml").write_text(sitemap(recs), encoding="utf-8")
    (SITE / "robots.txt").write_text(robots(), encoding="utf-8")
    (SITE / "opensearch.xml").write_text(opensearch(), encoding="utf-8")
    (SITE / "feed.xml").write_text(feed(recs), encoding="utf-8")
    dumps(recs)
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"site: {len(recs)} kind pages · {n_pages} picture pages · {n_img} images · {size:.1f} MB → {SITE}  ({time.time()-t0:.1f}s)  SITE_URL={SITE_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
