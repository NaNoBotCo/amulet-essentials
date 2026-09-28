#!/usr/bin/env python3
"""pieces_ingest.py — Nan's own photographs → the pictures a piece page shows.

A piece is one physical object someone here photographed: data/pieces/<id>.json names it
and lists its Google Photos ids (`photos`) in the order they should appear. The raw files
sit in data/own_raw/ (gitignored: originals, full EXIF). This writes, per piece:

    data/own/<id>/<id>-<k>.jpg      each photo, upright, long edge ≤ 2000 px, no EXIF
    data/own/<id>/<id>-cutout.png   the subject lifted off its cloth (Apple Vision, on this
                                    Mac, tools/cutout), long edge ≤ 1600 px, transparent
    data/own/<id>/<id>-cutout.webp  the same for the page, long edge ≤ 900 px

and records them under `media` in the piece record (sha256, size, role). `hero` in the
record says which Vision instances make the cutout: [1], [2], "all", or null for no cutout
(a hand, a shirt or a coin would come with it). `rotate`: degrees clockwise.

    .venv/bin/python tools/pieces_ingest.py            # every piece, skipping done files
    .venv/bin/python tools/pieces_ingest.py --force <id> …
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA  # noqa: E402

PIECES = DATA / "pieces"
OWN = DATA / "own"
RAW = DATA / "own_raw"
CUTOUT = Path(__file__).resolve().parent / "cutout" / "cutout"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def raw_for(photo_id: str) -> Path | None:
    for ext in (".jpg", ".png"):
        p = RAW / f"gp-{photo_id}{ext}"
        if p.exists():
            return p
    return None


def save_photo(src: Path, dst: Path, edge: int = 2000, rotate: int = 0):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if rotate:
        im = im.rotate(-rotate, expand=True)
    im.thumbnail((edge, edge), Image.LANCZOS)
    im.save(dst, "JPEG", quality=86, optimize=True, progressive=True)   # no exif= → none written


def cut(src: Path, hero, png: Path, webp: Path, rotate: int = 0):
    inst = "all" if hero == "all" else ",".join(str(i) for i in hero)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / "c.png"
        r = subprocess.run([str(CUTOUT), str(src), str(tmp), inst], capture_output=True, text=True)
        if r.returncode or not tmp.exists():
            raise RuntimeError(f"cutout failed: {r.stdout} {r.stderr}")
        im = Image.open(tmp).convert("RGBA")
    if rotate:
        im = im.rotate(-rotate, expand=True)
    big = im.copy()
    big.thumbnail((1600, 1600), Image.LANCZOS)
    big.save(png, "PNG", optimize=True)
    small = im.copy()
    small.thumbnail((900, 900), Image.LANCZOS)
    small.save(webp, "WEBP", quality=86, method=6)


def media_entry(p: Path, role: str) -> dict:
    with Image.open(p) as im:
        w, h = im.size
    return {"file": f"{p.parent.name}/{p.name}", "role": role, "sha256": sha(p), "width": w, "height": h}


def ingest(rec: dict, force: bool) -> dict:
    pid = rec["id"]
    d = OWN / pid
    d.mkdir(parents=True, exist_ok=True)
    media = []
    for k, ph in enumerate(rec["photos"], 1):
        dst = d / f"{pid}-{k}.jpg"
        if force or not dst.exists():
            src = raw_for(ph)
            if not src:
                print(f"  ! {pid}: raw photo {ph} not in data/own_raw — skipped")
                continue
            save_photo(src, dst, rotate=rec.get("rotate", 0))
        media.append(media_entry(dst, "photo"))
    if rec.get("hero"):
        png, webp = d / f"{pid}-cutout.png", d / f"{pid}-cutout.webp"
        if force or not (png.exists() and webp.exists()):
            src = raw_for(rec["photos"][0])
            if src:
                cut(src, rec["hero"], png, webp, rotate=rec.get("rotate", 0))
        if png.exists():
            media.insert(0, media_entry(png, "cutout"))
            media.insert(1, media_entry(webp, "cutout_web"))
    rec["media"] = media
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args()
    n = 0
    for p in sorted(PIECES.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if a.ids and rec["id"] not in a.ids:
            continue
        rec = ingest(rec, a.force)
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n += 1
    print(f"pieces_ingest: {n} pieces → {OWN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
