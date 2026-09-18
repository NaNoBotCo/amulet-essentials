#!/usr/bin/env python3
"""harvest_commons.py — free-to-use images from Wikimedia Commons, with their licences attached.

Two modes, both polite (1 request/second, a named User-Agent, resumable):

  --walk "Category:Buddhist amulets of Thailand"
      List a category's files with licence + author into data/images/_triage/<category>.json.
      Downloads nothing. This is how a category gets read before anything is assigned.

  --harvest [id ...]
      For each record (all, or the ids given) fetch media.commons_files and every file in
      media.commons_categories, keep only files whose licence is on the free allowlist
      (CC0 / public domain / CC BY / CC BY-SA), download a 1200px rendition to
      data/images/<id>/, write a sidecar .json beside it, and — only with --apply — merge
      the image into the record's images[] (idempotent on the Commons title).

Nothing here ever asserts a licence: it records what Commons says, file by file, and a
file whose licence cannot be read is skipped and reported.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, KINDS, jdump, jload, load_kinds  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = "amulet-essentials/0.1 (https://wichaa.net; research catalogue of Thai sacred objects)"
FREE = re.compile(r"^(CC0(\s*1\.0)?|Public domain|PD(-[A-Za-z0-9-]+)?|CC[- ]BY(-SA)?(\s*[1-4]\.[0-9])?|FAL(\s*1\.[0-9])?)$", re.I)
DELAY = 1.0
_last = [0.0]


def _retry(fn, what: str):
    """Five attempts, backing off 2·4·8·16 s. A DNS hiccup or a dropped socket on a
    long harvest is routine, not a reason to lose the run."""
    for attempt in range(5):
        try:
            return fn()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt == 4:
                raise
            print(f"  retry {attempt + 1}/4 after {type(e).__name__} on {what}", file=sys.stderr)
            time.sleep(2 ** (attempt + 1))


def _get(params: dict) -> dict:
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    params = dict(params, format="json", formatversion="2")
    # POST: a batch of Thai file titles percent-encodes past the GET URL limit (HTTP 414).
    req = urllib.request.Request(API, data=urllib.parse.urlencode(params).encode(), headers={"User-Agent": UA})

    def go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    out = _retry(go, params.get("action", "api"))
    _last[0] = time.time()
    return out


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def category_files(cat: str) -> list[str]:
    if not cat.startswith("Category:"):
        cat = "Category:" + cat
    out, cont = [], {}
    while True:
        d = _get({"action": "query", "list": "categorymembers", "cmtitle": cat, "cmtype": "file", "cmlimit": 500, **cont})
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        cont = d.get("continue", {})
        if not cont:
            return out


def file_info(titles: list[str], width=1200) -> list[dict]:
    """imageinfo + extmetadata for up to 50 titles."""
    out = []
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        d = _get({"action": "query", "prop": "imageinfo", "titles": "|".join(chunk),
                  "iiprop": "url|extmetadata|sha1|size|mime", "iiurlwidth": width})
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            g = lambda k: _strip((em.get(k) or {}).get("value", ""))  # noqa: E731
            out.append({
                "title": p.get("title"),
                "page_url": ii.get("descriptionshorturl") or ii.get("descriptionurl"),
                "url": ii.get("url"),
                "thumb_url": ii.get("thumburl") or ii.get("url"),
                "sha1": ii.get("sha1"),
                "width": ii.get("width"), "height": ii.get("height"), "mime": ii.get("mime"),
                "license": g("LicenseShortName"),
                "license_url": g("LicenseUrl"),
                "author": g("Artist"),
                "credit": g("Credit"),
                "attribution": g("Attribution"),
                "description": g("ImageDescription")[:400],
                "date": g("DateTimeOriginal"),
                "categories": g("Categories"),
                "free": bool(FREE.match(g("LicenseShortName"))),
            })
    return out


def walk(cat: str) -> Path:
    files = category_files(cat)
    info = file_info(files) if files else []
    out = IMAGES / "_triage" / (re.sub(r"[^A-Za-z0-9]+", "_", cat.replace("Category:", "")).strip("_") + ".json")
    jdump({"category": cat, "count": len(info), "free": sum(1 for f in info if f["free"]), "files": info}, out)
    print(f"{cat}: {len(info)} files, {sum(1 for f in info if f['free'])} free → {out}")
    return out


def _download(url: str, dest: Path) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    def go():
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    data = _retry(go, dest.name)
    _last[0] = time.time()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def set_primary(rec: dict) -> None:
    """The lead picture is the first of the record's own `commons_files` (the agent
    chose those deliberately), then the first category file. Never a random API order."""
    imgs = rec.get("images") or []
    if not imgs:
        return
    for im in imgs:
        im.pop("primary", None)
    wanted = [t if t.startswith("File:") else "File:" + t for t in (rec.get("media") or {}).get("commons_files") or []]
    by_title = {im.get("title"): im for im in imgs}
    pick = next((by_title[t] for t in wanted if t in by_title), imgs[0])
    pick["primary"] = True
    imgs.remove(pick)
    imgs.insert(0, pick)


def prune(rec: dict, n: int) -> int:
    """Keep the record's own commons_files first, then the earliest category pulls, up to n."""
    imgs = rec.get("images") or []
    if len(imgs) <= n:
        return 0
    wanted = [t if t.startswith("File:") else "File:" + t for t in (rec.get("media") or {}).get("commons_files") or []]
    own = [im for im in imgs if im.get("title") in wanted]
    rest = [im for im in imgs if im.get("title") not in wanted]
    keep = (own + rest)[:n]
    drop = [im for im in imgs if im not in keep]
    for im in drop:
        f = IMAGES / im["file"]
        for path in (f, f.with_suffix(f.suffix + ".json")):
            if path.exists():
                path.unlink()
    rec["images"] = keep
    set_primary(rec)
    return len(drop)


def harvest(rec: dict, apply=False, width=1200, cap=24) -> list[dict]:
    media = rec.get("media") or {}
    named = [t if t.startswith("File:") else "File:" + t for t in dict.fromkeys(media.get("commons_files") or [])]
    from_cat: list[str] = []
    for cat in media.get("commons_categories") or []:
        from_cat += category_files(cat)
    from_cat = [t if t.startswith("File:") else "File:" + t for t in dict.fromkeys(from_cat) if t not in set(named)]
    # A category can hold hundreds of files (Category:Kris: 344). The record's own named
    # picks are ALWAYS fetched; the category only tops the record up to `cap` pictures.
    # (An earlier version sliced the combined list, which silently dropped the named
    # picks whenever the record already held pictures — a whole harvest merged nothing.)
    have_titles = {im.get("title") for im in rec.get("images") or []}
    cat_room = max(0, cap - sum(1 for t in have_titles if t not in set(named)))
    titles = named + from_cat[:cat_room]
    if not titles:
        return []
    have = {im.get("title") for im in rec.get("images", [])}
    added = []
    for f in file_info(titles, width):
        if not f["title"] or not f["thumb_url"]:
            continue
        if not f["free"]:
            print(f"  skip {f['title']}  licence {f['license']!r} not free")
            continue
        if f["title"] in have:
            continue
        ext = ".jpg" if "jpeg" in (f["mime"] or "") or f["thumb_url"].lower().endswith(".jpg") else Path(urllib.parse.urlparse(f["thumb_url"]).path).suffix or ".jpg"
        # Descriptive filename: the kind first (what a reverse-image search should learn),
        # then any Latin words the Commons title had, then a short hash so re-uploads never collide.
        latin = re.sub(r"-(jpe?g|png|gif|webp|tiff?)$", "", re.sub(r"[^a-z0-9]+", "-", f["title"][5:].lower()).strip("-"))[:40].strip("-")
        rel = f"{rec['id']}/{rec['id']}{('-' + latin) if latin else ''}-{(f['sha1'] or 'x')[:6]}{ext}"
        dest = IMAGES / rel
        if not dest.exists():
            sha = _download(f["thumb_url"], dest)
        else:
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        entry = {
            "file": rel, "source": "commons", "title": f["title"], "url": f["url"], "page_url": f["page_url"],
            "license": f["license"], "license_url": f["license_url"], "author": f["author"] or f["attribution"],
            "credit": f["credit"], "view": "other",
            "alt_th": rec["names"]["th"], "alt_en": f"{rec['names']['en']} — {f['description'][:120]}".strip(" —"),
            "sha256": sha, "width": f["width"] or 0, "height": f["height"] or 0,
        }
        jdump({**entry, "commons": f}, dest.with_suffix(dest.suffix + ".json"))
        added.append(entry)
        print(f"  + {rel}  [{f['license']}]  {f['author'][:40]}")
    if apply and added:
        rec.setdefault("images", []).extend(added)
        set_primary(rec)
        clean = {k: v for k, v in rec.items() if not k.startswith("_")}
        jdump(clean, KINDS / f"{rec['id']}.json")
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--walk", action="append", default=[], help="Category to list into _triage (repeatable)")
    ap.add_argument("--harvest", nargs="*", help="record ids (none = all records with media targets)")
    ap.add_argument("--apply", action="store_true", help="merge harvested images into the records")
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--reprimary", action="store_true", help="re-pick the lead picture of every record (no network)")
    ap.add_argument("--cap", type=int, default=24, help="max pictures pulled per record from categories (its own commons_files always come first)")
    ap.add_argument("--prune", type=int, help="drop pictures beyond N per record (commons_files kept first) and delete their files")
    ap.add_argument("--dedupe", action="store_true", help="resolve pictures claimed by more than one record (no network)")
    a = ap.parse_args()
    if a.dedupe:
        # A picture claimed by several records is evidence for the CATEGORY it came from,
        # not for any one kind: six Buddha-tablet records each pulled the whole of
        # "Buddhist amulets of Thailand", so twelve photographs belonged to all six at
        # once, and the identifier could not tell those kinds apart — it was being asked
        # to separate kinds using pictures that do not separate them.
        # Rule: a contested picture stays only with a record that NAMED it in its own
        # media.commons_files. If no record named it, no record keeps it.
        recs = load_kinds()
        claims: dict = {}
        for r in recs:
            for im in r.get("images") or []:
                claims.setdefault(im.get("sha256"), []).append(r["id"])
        contested = {sha for sha, ids in claims.items() if len(set(ids)) > 1}
        named = {r["id"]: {t if t.startswith("File:") else "File:" + t
                           for t in (r.get("media") or {}).get("commons_files") or []} for r in recs}
        removed = kept = 0
        for r in recs:
            before = r.get("images") or []
            after = [im for im in before
                     if im.get("sha256") not in contested or im.get("title") in named[r["id"]]]
            if len(after) != len(before):
                removed += len(before) - len(after)
                kept += sum(1 for im in after if im.get("sha256") in contested)
                r["images"] = after
                set_primary(r)
                jdump({k: v for k, v in r.items() if not k.startswith("_")}, KINDS / f"{r['id']}.json")
                print(f"  {r['id']}: {len(before)} → {len(after)}")
        # files are content-addressed and may still be claimed elsewhere; delete only orphans
        still = {im.get("sha256") for r in load_kinds() for im in r.get("images") or []}
        orphans = 0
        for sha in contested - still:
            for f in IMAGES.glob(f"*/*"):
                if f.suffix == ".json":
                    continue
                try:
                    meta = jload(f.with_suffix(f.suffix + ".json")) if f.with_suffix(f.suffix + ".json").exists() else {}
                except Exception:  # noqa: BLE001
                    meta = {}
                if meta.get("sha256") == sha:
                    f.unlink(missing_ok=True)
                    f.with_suffix(f.suffix + ".json").unlink(missing_ok=True)
                    orphans += 1
        print(f"{len(contested)} contested picture(s): {removed} claim(s) dropped, {kept} kept by the record that named them, {orphans} file(s) deleted")
        return 0
    if a.prune:
        dropped = 0
        for r in load_kinds():
            d = prune(r, a.prune)
            if d:
                dropped += d
                jdump({k: v for k, v in r.items() if not k.startswith("_")}, KINDS / f"{r['id']}.json")
                print(f"  {r['id']}: dropped {d}")
        print(f"pruned {dropped} picture(s) beyond {a.prune} per record")
        return 0
    if a.reprimary:
        for r in load_kinds():
            if r.get("images"):
                set_primary(r)
                jdump({k: v for k, v in r.items() if not k.startswith("_")}, KINDS / f"{r['id']}.json")
        print("lead pictures re-picked")
        return 0
    for cat in a.walk:
        walk(cat)
    if a.harvest is not None:
        recs = load_kinds()
        if a.harvest:
            recs = [r for r in recs if r["id"] in set(a.harvest)]
        total = 0
        failed = []
        for r in recs:
            if not (r.get("media") or {}):
                continue
            print(r["id"])
            try:
                total += len(harvest(r, apply=a.apply, width=a.width, cap=a.cap))
            except Exception as e:  # noqa: BLE001
                failed.append(r["id"])
                print(f"  ! {r['id']}: {type(e).__name__}: {e}")
        if failed:
            print(f"failed (re-run for these): {' '.join(failed)}")
        print(f"{total} image(s) {'merged' if a.apply else 'downloaded (not merged — add --apply)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
