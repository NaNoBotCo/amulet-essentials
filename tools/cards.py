#!/usr/bin/env python3
"""cards.py — share cards for wichaa.net/amulets: one master, one per kind.

Rendered with Chrome through manuscript-wiki/make_card.py's `render` (the fleet card
engine: 1200×630, Georgia titles, Thai-capable font), written as committed masters into
manuscript-wiki/publishing/cards/ — `amulets.png` and `amulets__kind__<id>.png` — which
site_meta.py copies to /amulets/card.png and /amulets/kind/<id>/card.png on publish.
site.py points each page's og:image at its card when the master exists.

A kind's card is its own picture (the primary, embedded as a data URI, cropped to the right
half) beside its Thai name, romanisation, English gloss and class. Kinds without a picture
get a text card. Re-run after new pictures land; unchanged kinds are skipped unless --force.

    python3 tools/cards.py            # master + every kind
    python3 tools/cards.py phra-somdet hun-phayon
"""
from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, IMAGES, PROJECTS, jload  # noqa: E402

WIKI = PROJECTS / "manuscript-wiki"
sys.path.insert(0, str(WIKI))
import make_card  # noqa: E402  (fleet card engine: _card_shell, _CARD_FONT, render)

CARDS = WIKI / "publishing" / "cards"
E = html.escape


def _fit(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars - 1].rstrip() + "…"


def kind_card_svg(r: dict) -> str:
    n = r["names"]
    cf = r["class_facts"]
    prim = r.get("primary_image")
    F = make_card._CARD_FONT
    pic = ""
    if prim and (IMAGES / prim["file"]).exists():
        p = IMAGES / prim["file"]
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        pic = (f'<clipPath id="c"><rect x="640" y="16" width="560" height="614"/></clipPath>'
               f'<image clip-path="url(#c)" x="640" y="16" width="560" height="614" preserveAspectRatio="xMidYMid slice" '
               f'href="data:{mime};base64,{b64}"/>'
               f'<rect x="640" y="16" width="560" height="614" fill="none"/>')
    cls = f'{cf.get("term") or "ยังไม่ชี้ขาด"} · {cf.get("en_gloss") or "left to a knower"}'
    resident = f'resident: {cf.get("resident") or "—"} · upkeep: {cf.get("upkeep") or "—"}'
    what = _fit(r["text"]["what_en"], 150)
    # wrap `what` into ≤3 lines of ~44 chars
    words, lines, cur = what.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 46 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    lines = lines[:3]
    what_svg = "".join(f'<text x="66" y="{452 + i * 30}" font-family="{F}" font-size="22" fill="#3a4a47">{E(l)}</text>' for i, l in enumerate(lines))
    right_w = 560 if pic else 0
    title_size = 64 if len(n["th"]) <= 9 else 52 if len(n["th"]) <= 13 else 42
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#f4f7f6"/>
<rect x="0" y="0" width="1200" height="16" fill="#1F4E4A"/>
{pic}
<text x="66" y="110" font-family="Georgia,serif" font-size="26" fill="#1F4E4A" letter-spacing="6">WICHAA · AMULETS</text>
<text x="66" y="220" font-family="{F}" font-size="{title_size}" font-weight="700" fill="#141b1a">{E(_fit(n["th"], 18))}</text>
<text x="66" y="268" font-family="Georgia,serif" font-size="30" fill="#1F4E4A">{E(_fit(n["roman"], 30))}</text>
<text x="66" y="310" font-family="{F}" font-size="26" fill="#3a4a47">{E(_fit(n["en"], 40))}</text>
<rect x="66" y="346" rx="22" width="{min(540, 40 + int(len(cls) * 11.5))}" height="44" fill="#ffffff" stroke="#d7e0dd"/>
<text x="{66 + min(540, 40 + int(len(cls) * 11.5)) / 2:.0f}" y="375" font-family="{F}" font-size="20" fill="#1F4E4A" text-anchor="middle">{E(_fit(cls, 46))}</text>
<text x="66" y="418" font-family="{F}" font-size="20" fill="#3a4a47">{E(resident)}</text>
{what_svg}
<text x="66" y="580" font-family="{F}" font-size="20" fill="#3a4a47">wichaa.net/amulets/kind/{E(r["id"])}</text>
</svg>"""


def master_card_svg(recs: list[dict]) -> str:
    F = make_card._CARD_FONT
    n_img = sum(len(r.get("images", [])) for r in recs)
    regions = len({rg for r in recs for rg in r["region"]})
    # mosaic of 12 primary pictures across the bottom
    tiles, x = [], 66
    picks = [r for r in recs if r.get("primary_image")][:12]
    for r in picks:
        p = IMAGES / r["primary_image"]["file"]
        if not p.exists():
            continue
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        cid = f"m{len(tiles)}"
        tiles.append(f'<clipPath id="{cid}"><rect x="{x}" y="430" rx="10" width="84" height="110"/></clipPath>'
                     f'<image clip-path="url(#{cid})" x="{x}" y="430" width="84" height="110" preserveAspectRatio="xMidYMid slice" href="data:{mime};base64,{b64}"/>')
        x += 92
    body = (f'<text x="66" y="352" font-family="{F}" font-size="44" font-weight="700" fill="#141b1a">สารบบเครื่องราง — '
            f'<tspan fill="#1F4E4A">is anyone home?</tspan></text>'
            f'<text x="66" y="396" font-family="{F}" font-size="24" fill="#3a4a47">Thai · Khmer · Lao · Burmese · Malay · Vietnamese · Chinese-SE-Asian — with pictures and provenance</text>'
            + "".join(tiles))
    return make_card._card_shell(
        ["Amulet Essentials"],
        f"{len(recs)} kinds · {n_img} free-to-use pictures · {regions} regions · every field says where it came from",
        "wichaa.net/amulets", body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-master", action="store_true")
    a = ap.parse_args()
    recs = jload(BUILD / "api" / "kinds.json")["kinds"]
    CARDS.mkdir(parents=True, exist_ok=True)
    done = 0
    if not a.no_master and not a.ids:
        make_card.render(master_card_svg(recs), CARDS / "amulets.png")
        print(f"amulets card → {CARDS / 'amulets.png'}")
        done += 1
    for r in recs:
        if a.ids and r["id"] not in a.ids:
            continue
        out = CARDS / f"amulets__kind__{r['id']}.png"
        src = IMAGES / r["primary_image"]["file"] if r.get("primary_image") else None
        if out.exists() and not a.force and (not src or src.stat().st_mtime < out.stat().st_mtime):
            continue
        make_card.render(kind_card_svg(r), out)
        done += 1
        print(f"  {r['id']} → {out.name}")
    print(f"{done} card(s) rendered into {CARDS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
