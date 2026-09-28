#!/usr/bin/env python3
"""piece_cards.py — 1200×630 share cards for /pieces/: one per piece, one for the index.

Background · scrim · spacer · text. A piece with a cutout floats it on a lamp-lit lacquer
ground with a gold halo; a piece without one (hand, shirt or coin in frame) shows its first
photo on the right under a scrim. Thai set in Sukhumvit Set through PIL's raqm layout,
which keeps stacked tone marks.

    .venv/bin/python tools/piece_cards.py          # every piece + data/own/_index-card.jpg
    .venv/bin/python tools/piece_cards.py <id> …
    .venv/bin/python tools/piece_cards.py --site <out.png>   # the /amulets master card
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA  # noqa: E402

PIECES, OWN = DATA / "pieces", DATA / "own"
W, H = 1200, 630
SUK = "/System/Library/Fonts/Supplemental/SukhumvitSet.ttc"
GEORGIA = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GOLD, INK, MUTE = (232, 200, 114), (246, 238, 222), (190, 176, 150)


def font(size: int, bold=True, serif=False):
    if serif:
        return ImageFont.truetype(GEORGIA, size)
    return ImageFont.truetype(SUK, size, index=5 if bold else 2)


def ground(seed: int) -> Image.Image:
    """Lacquer-dark ground, a warm lamp to the right, a scatter of gold motes."""
    im = Image.new("RGB", (W, H), (14, 11, 8))
    glow = Image.new("L", (W, H), 0)
    g = ImageDraw.Draw(glow)
    cx, cy = int(W * 0.72), int(H * 0.5)
    for r in range(430, 0, -6):
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=int(150 * (1 - r / 430) ** 1.6))
    im.paste(Image.new("RGB", (W, H), (120, 78, 28)), (0, 0), glow.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(im)
    rnd = random.Random(seed)
    for _ in range(70):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        a = rnd.random()
        c = tuple(int(v * (0.25 + 0.6 * a)) for v in GOLD)
        s = 1 if a < 0.8 else 2
        d.ellipse([x - s, y - s, x + s, y + s], fill=c)
    # halo ring
    ring = Image.new("L", (W, H), 0)
    ImageDraw.Draw(ring).ellipse([cx - 250, cy - 250, cx + 250, cy + 250], outline=90, width=2)
    im.paste(Image.new("RGB", (W, H), GOLD), (0, 0), ring.filter(ImageFilter.GaussianBlur(1.2)))
    return im


def float_cutout(base: Image.Image, cut: Image.Image, box=(660, 40, 1160, 590)):
    bw, bh = box[2] - box[0], box[3] - box[1]
    c = cut.copy()
    c.thumbnail((bw, bh), Image.LANCZOS)
    x = box[0] + (bw - c.width) // 2
    y = box[1] + (bh - c.height) // 2
    a = c.split()[3]
    glow = Image.new("L", base.size, 0)
    glow.paste(a, (x, y))
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    base.paste(Image.new("RGB", base.size, (255, 196, 90)), (0, 0), glow.point(lambda v: int(v * 0.55)))
    shadow = Image.new("L", base.size, 0)
    shadow.paste(a, (x + 10, y + 16))
    base.paste(Image.new("RGB", base.size, (0, 0, 0)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.6)))
    base.paste(c, (x, y), c)


def photo_right(base: Image.Image, photo: Image.Image):
    p = ImageOps.fit(photo.convert("RGB"), (640, H), Image.LANCZOS, centering=(0.5, 0.45))
    base.paste(p, (W - 640, 0))
    scrim = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(scrim)
    for x in range(W - 640, W - 300):
        sd.line([(x, 0), (x, H)], fill=int(255 * (1 - (x - (W - 640)) / 340) ** 1.4))
    base.paste(Image.new("RGB", (W, H), (14, 11, 8)), (0, 0), scrim)


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int, lines: int) -> list[str]:
    words, out, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,") + "…"
    return out


def text_block(base: Image.Image, th: str, en: str, kicker: str, foot: str):
    d = ImageDraw.Draw(base)
    x, y = 64, 70
    d.text((x, y), kicker, font=font(26, bold=False), fill=GOLD)
    y += 58
    for ln in wrap(d, th, font(60), 560, 3):
        d.text((x, y), ln, font=font(60), fill=INK)
        y += 84
    y += 8
    for ln in wrap(d, en, font(34, serif=True), 560, 3):
        d.text((x, y), ln, font=font(34, serif=True), fill=MUTE)
        y += 46
    d.line([(x, H - 92), (x + 70, H - 92)], fill=GOLD, width=3)
    d.text((x, H - 76), foot, font=font(24, bold=False), fill=MUTE)


def card(rec: dict) -> Path:
    pid = rec["id"]
    base = ground(sum(map(ord, pid)))
    cut = OWN / pid / f"{pid}-cutout.png"
    if cut.exists():
        float_cutout(base, Image.open(cut).convert("RGBA"))
    else:
        photo_right(base, Image.open(OWN / pid / f"{pid}-1.jpg"))
    kicker = "พระประจำวัน · Buddhas of the days" if rec.get("set") == "days" else "ชิ้นต่อชิ้น · Pieces"
    text_block(base, rec["names"]["th"], rec["names"]["en"], kicker, "wichaa.net/amulets · สารบบเครื่องราง")
    out = OWN / pid / f"{pid}-card.jpg"
    base.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def index_card(recs: list[dict]) -> Path:
    base = ground(7)
    cuts = [OWN / r["id"] / f"{r['id']}-cutout.png" for r in recs if (OWN / r["id"] / f"{r['id']}-cutout.png").exists()]
    pick = ["garuda-round-case", "ngang-gold", "jade-qilin-pendant", "turtle-medallion", "hongshan-sun-gods",
            "khun-phaen-red-enamel", "brass-rooster", "somdet-enamel-frame", "hanuman-arch-case"]
    chosen = [OWN / p / f"{p}-cutout.png" for p in pick if (OWN / p / f"{p}-cutout.png").exists()] or cuts[:9]
    cx, cy = 900, 315
    for i, p in enumerate(chosen):
        ang = -math.pi / 2 + i * 2 * math.pi / len(chosen)
        r = 215
        bx, by = int(cx + r * math.cos(ang)), int(cy + r * math.sin(ang))
        float_cutout(base, Image.open(p).convert("RGBA"), (bx - 70, by - 70, bx + 70, by + 70))
    text_block(base, "ชิ้นต่อชิ้น", f"Pieces — {len(recs)} amulets and sacred figures, photographed one by one",
               "สารบบเครื่องราง · Amulet Essentials", "wichaa.net/amulets/pieces")
    out = OWN / "_index-card.jpg"
    base.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def site_card(recs: list[dict], out: Path) -> Path:
    """The /amulets master card (publishing/cards/amulets.png): the pieces in a ring, the counts."""
    base = ground(3)
    pick = ["ngang-gold", "garuda-round-case", "hun-payont-first", "jade-qilin-pendant", "turtle-medallion",
            "hongshan-sun-gods", "khun-phaen-red-enamel", "naga-eye-four-nagas", "brass-rooster", "somdet-enamel-frame"]
    chosen = [OWN / p / f"{p}-cutout.png" for p in pick if (OWN / p / f"{p}-cutout.png").exists()]
    cx, cy = 900, 315
    for i, p in enumerate(chosen):
        ang = -math.pi / 2 + i * 2 * math.pi / len(chosen)
        bx, by = int(cx + 222 * math.cos(ang)), int(cy + 222 * math.sin(ang))
        float_cutout(base, Image.open(p).convert("RGBA"), (bx - 64, by - 64, bx + 64, by + 64))
    kinds = json.loads((DATA.parent / "build" / "api" / "kinds.json").read_text(encoding="utf-8"))["kinds"]
    n_pic = sum(len(k.get("images", [])) for k in kinds) + sum(len([m for m in r.get("media", []) if m["role"] == "photo"]) for r in recs)
    text_block(base, "สารบบเครื่องราง", f"Amulet Essentials — {len(kinds)} kinds, {len(recs)} pieces, {n_pic:,} pictures, Thai and English",
               "wichaa · วิชา", "wichaa.net/amulets")
    base.save(out, "PNG", optimize=True)
    return out


def main() -> int:
    if sys.argv[1:2] == ["--site"]:
        recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PIECES.glob("*.json"))]
        print(site_card(recs, Path(sys.argv[2])))
        return 0
    ids = set(sys.argv[1:])
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PIECES.glob("*.json"))]
    n = 0
    for r in recs:
        if ids and r["id"] not in ids:
            continue
        card(r)
        n += 1
    if not ids:
        index_card(recs)
    print(f"piece_cards: {n} cards" + ("" if ids else " + index"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
