#!/usr/bin/env python3
"""hunt_commons.py — a systematic search of Wikimedia Commons for every kind, not the one
query an agent happened to try.

For each record (or the ids given) it runs one Commons search per name and alias — Thai,
romanised, English — plus a handful of kind-specific extra terms, pools the file hits,
checks every candidate's licence through imageinfo/extmetadata, drops what any record
already holds or what is already assigned to a DIFFERENT record (a contested picture is
evidence for nobody — the dedupe rule), and writes the survivors to
data/images/_hunt/<id>.json with title, licence, author, size and a thumbnail URL, ranked
by a relevance heuristic (title carries a name of the kind, then file size).

It downloads nothing and assigns nothing. `--apply N` writes the top-N candidates into the
record's media.commons_files, after which harvest_commons.py --harvest <id> --apply fetches
them. Two steps on purpose: a search hit is a lead, not evidence.

    python3 tools/hunt_commons.py                 # every record
    python3 tools/hunt_commons.py hun-phayon bia-kae --apply 8
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, KINDS, jdump, load_kinds  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = "amulet-essentials/0.1 (https://wichaa.net; research catalogue of Thai sacred objects)"
FREE = re.compile(r"^(CC0(\s*1\.0)?|Public domain|PD(-[A-Za-z0-9-]+)?|CC[- ]BY(-SA)?(\s*[1-4]\.[0-9])?|FAL)$", re.I)
HUNT = IMAGES / "_hunt"
DELAY = 0.7
_last = [0.0]

# Extra search terms per kind where the record's own names are unlikely to match a Commons
# title (Commons titles are mostly English, occasionally Thai).
EXTRA = {
    "bia-kae": ["cowrie amulet", "bia gae", "cowry shell charm Thailand"],
    "mit-mo": ["ritual knife Thailand", "meed mor", "Thai ceremonial dagger"],
    "hun-phayon": ["hun payon", "straw effigy Thailand", "Thai effigy doll"],
    "jatukham": ["Jatukam Ramathep", "Chatukham", "จตุคาม"],
    "lek-lai": ["lek lai", "เหล็กไหล"],
    "luk-om": ["luk om amulet"],
    "khiao-suea": ["tiger fang amulet", "tiger tooth amulet Thailand", "เขี้ยวเสือ"],
    "salika": ["salika amulet", "myna bird amulet Thailand", "สาลิกา"],
    "waan": ["wan amulet Thailand", "ว่าน"],
    "phra-khong": ["Phra Khong Lamphun", "พระคง"],
    "phra-hu-yan": ["Phra Hu Yan", "พระหูยาน", "Lopburi amulet"],
    "phra-khanaen": ["พระคะแนน"],
    "rup-lo": ["cast monk figure amulet", "รูปหล่อหลวงพ่อ", "Luang Phor statue amulet"],
    "rup-suea": ["carved tiger amulet Thailand", "Luang Pho Pan tiger"],
    "wua-thanu": ["wua thanu", "วัวธนู"],
    "waen-phirot": ["Thai ring amulet", "แหวนพิรอด"],
    "kala-ta-diao": ["one eyed coconut", "กะลาตาเดียว", "coconut Rahu amulet"],
    "khot-kala": ["คดกะลา"],
    "phaya-tao-ruean": ["turtle amulet Thailand", "Luang Pu Liu", "พญาเต่าเรือน"],
    "phra-phong-bai-lan": ["ผงใบลาน"],
    "si-phueng": ["สีผึ้ง", "Thai charm wax"],
    "nam-man-phrai": ["น้ำมันพราย", "prai oil"],
    "nang-phrai": ["นางพราย"],
    "luk-krok": ["ลูกกรอก"],
    "chan-mak": ["ชานหมาก", "betel quid relic"],
    "susuk": ["susuk implant", "charm needle"],
    "tangkal": ["tangkal Malay", "Malay amulet", "azimat"],
    "jenglot": ["jenglot"],
    "phat-ban-menh": ["Phật bản mệnh", "eight guardian Buddhas pendant"],
    "luk-sakot": ["ลูกสะกด"],
    "takrut": ["takrut", "ตะกรุด", "Thai amulet scroll"],
    "phra-pidta": ["Phra Pidta", "พระปิดตา", "Pidta amulet"],
    "phra-rot": ["Phra Rod", "พระรอด", "Lamphun amulet"],
    "kuman-thong": ["Kuman Thong", "กุมารทอง", "Guman Thong"],
    "khun-phaen": ["Khun Paen amulet", "ขุนแผน"],
    "locket": ["Thai locket amulet", "ล็อกเก็ตพระ"],
    "somdet-chitralada": ["Somdej Jitralada", "พระสมเด็จจิตรลดา"],
    "pha-yan": ["pha yant", "ผ้ายันต์", "yantra cloth Thailand"],
    "suea-yan": ["เสื้อยันต์", "yantra shirt"],
    "chingchok-song-hang": ["จิ้งจกสองหาง", "two tailed gecko"],
    "jimat": ["jimat", "Malay talisman", "Islamic amulet Malaysia"],
    "rajah": ["rajah talisman Java", "rajah Jawa"],
    "mustika": ["batu mustika", "mustika pearl", "bezoar Indonesia"],
    "bua": ["bùa", "Vietnamese talisman", "bùa hộ mệnh"],
    "fu-talisman": ["fu talisman", "fulu", "符"],
    "kuan-im": ["Guanyin pendant", "Kuan Yin amulet"],
    "dat-lone": ["dat lone", "ဓာတ်လုံး"],
    "khmer-katha": ["Khmer amulet", "katha Cambodia"],
    "ai-khai": ["Ai Khai", "ไอ้ไข่", "Wat Chedi Sichon"],
    "chuchok": ["Chuchok amulet", "ชูชก"],
    "phra-nang-phaya": ["Phra Nang Phaya", "พระนางพญา"],
    "phra-phong-suphan": ["Phra Phong Suphan", "พระผงสุพรรณ"],
    "phra-sum-ko": ["Phra Sum Kor", "พระซุ้มกอ"],
    "pla-taphian": ["pla taphian", "ปลาตะเพียน"],
}


def _get(params: dict) -> dict:
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    params = dict(params, format="json", formatversion="2")
    req = urllib.request.Request(API, data=urllib.parse.urlencode(params).encode(), headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                _last[0] = time.time()
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    return {}


def search_files(term: str, limit=40) -> list[str]:
    d = _get({"action": "query", "list": "search", "srsearch": term, "srnamespace": 6, "srlimit": limit})
    return [h["title"] for h in d.get("query", {}).get("search", [])]


def _strip(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def file_info(titles: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(titles), 50):
        d = _get({"action": "query", "prop": "imageinfo", "titles": "|".join(titles[i:i + 50]),
                  "iiprop": "url|extmetadata|sha1|size|mime", "iiurlwidth": 400})
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            g = lambda k: _strip((em.get(k) or {}).get("value", ""))  # noqa: E731
            lic = g("LicenseShortName")
            out.append({"title": p.get("title"), "license": lic, "free": bool(FREE.match(lic)), "author": g("Artist")[:80],
                        "desc": g("ImageDescription")[:200], "w": ii.get("width"), "h": ii.get("height"), "mime": ii.get("mime"),
                        "thumb": ii.get("thumburl"), "page": ii.get("descriptionshorturl"), "sha1": ii.get("sha1")})
    return out


def terms_for(rec: dict) -> list[str]:
    n = rec["names"]
    al = n.get("aliases") or {}
    ts = [n["th"], n["roman"], n["en"]] + al.get("th", []) + al.get("roman", []) + al.get("en", [])[:3] + EXTRA.get(rec["id"], [])
    ts += list((n.get("other_scripts") or {}).values())
    # strip parenthetical glosses from English names: "Bia kae (warding cowrie)" -> both halves
    more = []
    for t in ts:
        m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", t)
        if m:
            more += [m.group(1), m.group(2)]
    seen, out = set(), []
    for t in ts + more:
        t = t.strip()
        if len(t) >= 3 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:14]


def relevance(f: dict, rec: dict) -> float:
    names = [rec["names"]["th"], rec["names"]["roman"].lower(), rec["names"]["en"].lower().split(" (")[0]] + [a.lower() for a in (rec["names"].get("aliases") or {}).get("roman", [])] + (rec["names"].get("aliases") or {}).get("th", [])
    hay = (f["title"] + " " + f["desc"]).lower()
    score = sum(2.0 for nm in names if nm and nm.lower() in hay)
    if f.get("w") and f.get("h"):
        score += min(1.0, (f["w"] * f["h"]) / 4e6)
    if (f.get("mime") or "").endswith("svg"):
        score -= 3
    return score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--apply", type=int, help="write the top-N candidates into media.commons_files")
    ap.add_argument("--only-thin", type=int, help="only records with fewer than N pictures")
    a = ap.parse_args()
    recs = load_kinds()
    if a.ids:
        recs = [r for r in recs if r["id"] in set(a.ids)]
    if a.only_thin is not None:
        recs = [r for r in recs if len(r.get("images") or []) < a.only_thin]
    held = {}
    for r in load_kinds():
        for im in r.get("images") or []:
            held[im.get("title")] = r["id"]
    HUNT.mkdir(parents=True, exist_ok=True)
    summary = []
    for r in recs:
        titles = []
        for t in terms_for(r):
            try:
                titles += search_files(t)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {r['id']} {t!r}: {e}", file=sys.stderr)
        titles = [t for t in dict.fromkeys(titles) if t not in held or held[t] == r["id"]]
        titles = [t for t in titles if held.get(t) != r["id"]]
        if not titles:
            summary.append((r["id"], 0, 0))
            jdump({"id": r["id"], "candidates": []}, HUNT / f"{r['id']}.json")
            print(f"{r['id']:<22} 0 hits")
            continue
        info = [f for f in file_info(titles[:120]) if f.get("title")]
        free = [f for f in info if f["free"] and not (f.get("mime") or "").endswith("svg")]
        for f in free:
            f["rel"] = round(relevance(f, r), 2)
        free.sort(key=lambda f: -f["rel"])
        jdump({"id": r["id"], "searched": terms_for(r), "hits": len(info), "free": len(free), "candidates": free}, HUNT / f"{r['id']}.json")
        summary.append((r["id"], len(info), len(free)))
        print(f"{r['id']:<22} {len(info):>3} hits · {len(free):>3} free · top: " + " | ".join(f"{f['title'][5:40]}({f['rel']})" for f in free[:3]))
        if a.apply and free:
            media = r.setdefault("media", {})
            have = set(media.get("commons_files") or [])
            picks = [f["title"] for f in free if f["rel"] >= 1.0][:a.apply]
            if picks:
                media["commons_files"] = list(media.get("commons_files") or []) + [p for p in picks if p not in have]
                jdump({k: v for k, v in r.items() if not k.startswith("_")}, KINDS / f"{r['id']}.json")
    print(f"\n{len(summary)} records · {sum(1 for _, _, f in summary if f)} with free candidates · {sum(f for _, _, f in summary)} free candidates in all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
