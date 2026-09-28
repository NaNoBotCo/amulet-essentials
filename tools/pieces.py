"""pieces.py — /pieces/: single objects, photographed one by one, each lifted off its cloth.

A kind (data/kinds/) is a sort of thing; a piece (data/pieces/) is one thing someone here
held and photographed. Records are written by hand; tools/pieces_ingest.py fills `media`
(the photos and the cutout) and tools/piece_cards.py draws the share cards. site.py calls
render() after the kind pages, and kind_strip() inside every kind page.

Record fields: id · set ("pieces" | "days") · names{th,en} · kind (a kind id it resembles,
or null) · kind_how · photos (Google Photos ids, in order) · hero (Vision instances for the
cutout, or null) · taken · commons (bool: offered to Wikimedia Commons) · commons_files
(titles once uploaded) · text{th,en} · tier · order (days only) · media (generated).
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

E = html.escape
DAYS_TITLE = ("พระประจำวัน", "Buddhas of the days")
PIECE_CSS = """
.stage{position:relative;overflow:hidden;border-radius:14px;background:radial-gradient(ellipse at 50% 46%,#5a3d17 0%,#2a1d0e 42%,#120e09 78%);box-shadow:inset 0 0 0 1px rgba(232,200,114,.18)}
.stage::before{content:"";position:absolute;inset:-20%;background-image:radial-gradient(1.5px 1.5px at 12% 22%,#e8c872cc,transparent),radial-gradient(1px 1px at 78% 14%,#e8c87299,transparent),radial-gradient(1.5px 1.5px at 64% 72%,#e8c872aa,transparent),radial-gradient(1px 1px at 28% 84%,#e8c87288,transparent),radial-gradient(1px 1px at 90% 58%,#e8c872aa,transparent),radial-gradient(1.5px 1.5px at 40% 40%,#e8c87244,transparent);pointer-events:none}
.stage::after{content:"";position:absolute;left:50%;top:50%;width:78%;aspect-ratio:1;transform:translate(-50%,-50%);border-radius:50%;border:1px solid rgba(232,200,114,.22);pointer-events:none}
.stage img{position:relative;z-index:1;display:block;width:100%;height:100%;object-fit:contain;padding:9%;filter:drop-shadow(0 0 18px rgba(255,196,90,.35)) drop-shadow(0 10px 14px rgba(0,0,0,.55))}
.stage.photo img{padding:0;object-fit:cover;filter:none}
.stage.photo::after{display:none}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(10.5rem,1fr));gap:1rem;margin:.6rem 0 1.4rem}
.pcard{display:block;text-decoration:none;color:var(--ink)}.pcard .stage{aspect-ratio:1}
.pcard b{display:block;margin-top:.45rem;font-size:.95rem;line-height:1.3}.pcard span{display:block;color:var(--mute);font-size:.8rem;line-height:1.3}
.pcard:focus-visible{outline:3px solid var(--focus);outline-offset:3px;border-radius:14px}
.phero{max-width:34rem;margin:.4rem auto 1rem}.phero .stage{aspect-ratio:1}
.ptitle{text-align:center}.ptitle .th{font-size:2rem}.ptitle .roman{margin-top:.2rem}
.like{text-align:center;margin:.2rem 0 1rem}.like a{font-weight:600}
.pnav{display:flex;justify-content:space-between;gap:1rem;margin:1.4rem 0;font-size:.95rem}
.jump{display:flex;flex-wrap:wrap;gap:.3rem;margin:.4rem 0 1rem}
.band{display:grid;grid-template-columns:repeat(6,1fr);gap:.5rem;margin:.6rem 0 .4rem}.band .stage{aspect-ratio:1}
@media(max-width:560px){.pgrid{grid-template-columns:repeat(2,1fr);gap:.8rem}.pcard b{font-size:.88rem}.band{grid-template-columns:repeat(3,1fr)}.ptitle .th{font-size:1.6rem}}
@media (prefers-reduced-motion: no-preference){
 .stage::before{animation:motes 26s linear infinite}
 @keyframes motes{from{transform:translateY(0)}to{transform:translateY(-12%)}}
 .phero .stage img{animation:bob 7s ease-in-out infinite}
 @keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
 .pcard .stage img{transition:transform .35s ease,filter .35s ease}
 .pcard:hover .stage img,.pcard:focus-visible .stage img{transform:translateY(-5px) scale(1.04);filter:drop-shadow(0 0 26px rgba(255,200,100,.55)) drop-shadow(0 12px 14px rgba(0,0,0,.5))}
}
"""


def load(data: Path) -> list[dict]:
    d = data / "pieces"
    if not d.exists():
        return []
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]
    return sorted(recs, key=lambda r: (r.get("set") != "pieces", r.get("order", 0), r.get("taken") or "", r["id"]))


class Pieces:
    def __init__(self, recs, by_kind, site_url, image_base, rel, page, author, license_url, own_dir):
        self.recs, self.by_kind = recs, by_kind
        self.site_url, self.image_base, self.rel, self.page = site_url, image_base, rel, page
        self.author, self.license_url, self.own = author, license_url, own_dir
        self.by_id = {r["id"]: r for r in recs}

    # ---------------------------------------------------------------- media
    def src(self, m: dict, depth: int) -> str:
        if self.image_base:
            return f"{self.image_base}/{m['sha256']}{Path(m['file']).suffix.lower()}"
        return f"{self.rel(depth)}images/own/{m['file']}"

    def abs(self, m: dict) -> str:
        if self.image_base:
            return f"{self.image_base}/{m['sha256']}{Path(m['file']).suffix.lower()}"
        return f"{self.site_url}/images/own/{m['file']}"

    @staticmethod
    def role(r: dict, role: str) -> list[dict]:
        return [m for m in r.get("media", []) if m["role"] == role]

    def face(self, r: dict) -> tuple[dict | None, bool]:
        """The picture that stands for the piece: its cutout, else its first photo."""
        c = self.role(r, "cutout_web")
        if c:
            return c[0], True
        p = self.role(r, "photo")
        return (p[0] if p else None), False

    def card_media(self, r: dict) -> dict | None:
        f = self.own / r["id"] / f"{r['id']}-card.jpg"
        if not f.exists():
            return None
        import hashlib
        return {"file": f"{r['id']}/{f.name}", "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}

    def all_media(self) -> list[dict]:
        out = []
        for r in self.recs:
            out += r.get("media", [])
            c = self.card_media(r)
            if c:
                out.append(c)
        idx = self.own / "_index-card.jpg"
        if idx.exists():
            import hashlib
            out.append({"file": idx.name, "sha256": hashlib.sha256(idx.read_bytes()).hexdigest()})
        return out

    # ---------------------------------------------------------------- bits
    def stage(self, r: dict, depth: int, eager=False) -> str:
        m, cut = self.face(r)
        if not m:
            return '<div class="stage"></div>'
        alt = f'{r["names"]["th"]} · {r["names"]["en"]}'
        return (f'<div class="stage{"" if cut else " photo"}"><img src="{E(self.src(m, depth))}" alt="{E(alt)}" '
                f'width="{m["width"]}" height="{m["height"]}"{"" if eager else " loading=lazy"} decoding="async"></div>')

    def card(self, r: dict, depth: int) -> str:
        return (f'<a class="pcard" href="{self.rel(depth)}pieces/{E(r["id"])}/index.html">{self.stage(r, depth)}'
                f'<b class="th" lang="th">{E(r["names"]["th"])}</b><span>{E(r["names"]["en"])}</span></a>')

    def groups(self):
        kinds, loose, days = {}, [], []
        for r in self.recs:
            if r.get("set") == "days":
                days.append(r)
            elif r.get("kind") and r["kind"] in self.by_kind:
                kinds.setdefault(r["kind"], []).append(r)
            else:
                loose.append(r)
        return kinds, loose, days

    # ---------------------------------------------------------------- pages
    def index_page(self) -> str:
        d = 1
        kinds, loose, days = self.groups()
        n_photos = sum(len(self.role(r, "photo")) for r in self.recs)
        n_cut = sum(1 for r in self.recs if self.role(r, "cutout"))
        parts = [f'<nav class="crumbs"><a href="../index.html">Directory</a> › ชิ้นต่อชิ้น · Pieces</nav>',
                 '<h1><span class="th">ชิ้นต่อชิ้น</span> <span class="roman">Pieces · amulets and sacred figures, one at a time</span></h1>',
                 f'<p class="lede th" lang="th">พระเครื่อง เครื่องราง และรูปเคารพ {len(self.recs)} ชิ้น ถ่ายทีละชิ้น ภาพ {n_photos} ภาพ '
                 f'ยก {n_cut} ชิ้นออกจากผ้ารองให้เห็นองค์ชัด ๆ</p>',
                 f'<p class="lede" lang="en">{len(self.recs)} pieces, {n_photos} photographs, {n_cut} of them lifted off the cloth they were shot on. '
                 f'Each piece has its own page. Where one looks like a kind in the directory, it says so and links there.</p>']
        jumps = [f'<a class="chip" href="#k-{E(k)}">{E(self.by_kind[k]["names"]["th"])} ({len(v)})</a>' for k, v in sorted(kinds.items(), key=lambda kv: -len(kv[1]))]
        if loose:
            jumps.append(f'<a class="chip" href="#loose">ยังไม่จัดชนิด · not yet placed ({len(loose)})</a>')
        if days:
            jumps.append(f'<a class="chip" href="#days">{DAYS_TITLE[0]} ({len(days)})</a>')
        parts.append('<p class="jump">' + "".join(jumps) + "</p>")
        for k, rs in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
            kn = self.by_kind[k]["names"]
            parts.append(f'<h2 id="k-{E(k)}"><span class="th">{E(kn["th"])}</span> <span class="mute">{E(kn["en"])}</span> <span class="count">({len(rs)})</span> '
                         f'<a href="../kind/{E(k)}/index.html" style="font-size:.85rem">the kind →</a></h2>')
            parts.append('<div class="pgrid">' + "".join(self.card(r, d) for r in rs) + "</div>")
        if loose:
            parts.append(f'<h2 id="loose"><span class="th">ยังไม่จัดชนิด</span> <span class="mute">not yet placed in a kind</span> <span class="count">({len(loose)})</span></h2>')
            parts.append('<div class="pgrid">' + "".join(self.card(r, d) for r in loose) + "</div>")
        if days:
            parts.append(f'<h2 id="days"><span class="th">{DAYS_TITLE[0]}</span> <span class="mute">{DAYS_TITLE[1]}</span> <span class="count">({len(days)})</span></h2>'
                         '<p class="mute" style="font-size:.9rem">Eight carved wooden Buddhas, one posture for each day of the Thai week (Wednesday has two), photographed 29 August 2026. '
                         '<span class="th" lang="th">ปางประจำวันเกิด แปดปาง วันพุธแยกกลางวันกับกลางคืน</span></p>')
            parts.append('<div class="pgrid">' + "".join(self.card(r, d) for r in days) + "</div>")
        parts.append('<p class="legend">A kind link names what a piece resembles. It says nothing of age, maker or genuineness. '
                     'Photographs by Nan Peacock, licensed <a href="' + E(self.license_url) + '" rel="license">CC BY 4.0</a>. '
                     '<a href="../api/pieces.json">All pieces as JSON</a>.</p>')
        url = f"{self.site_url}/pieces/"
        ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "@id": url, "url": url, "name": "ชิ้นต่อชิ้น · Pieces",
               "inLanguage": ["th", "en"], "license": self.license_url, "creator": self.author,
               "hasPart": [{"@type": "ImageObject", "url": f"{self.site_url}/pieces/{r['id']}/", "name": f"{r['names']['th']} · {r['names']['en']}"} for r in self.recs]}]
        idx = self.own / "_index-card.jpg"
        extra = f"<style>{PIECE_CSS}</style>"
        if idx.exists():
            m = [x for x in self.all_media() if x["file"] == idx.name][0]
            extra += (f'<meta property="og:image" content="{E(self.abs(m))}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
                      f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{E(self.abs(m))}">')
        return self.page(f"ชิ้นต่อชิ้น · Pieces — {len(self.recs)} amulets and sacred figures", "\n".join(parts), d,
                         f"{len(self.recs)} Thai amulets, charms and sacred figures, photographed one by one and lifted off their cloth: Khun Phaen, Somdet, garuda, naga, jade, Buddhas of the days. Thai and English.",
                         ld, url, extra)

    def piece_page(self, r: dict) -> str:
        d = 2
        n = r["names"]
        order = self.recs
        i = order.index(r)
        prev_r, next_r = order[i - 1], order[(i + 1) % len(order)]
        parts = [f'<nav class="crumbs"><a href="../../index.html">Directory</a> › <a href="../index.html">ชิ้นต่อชิ้น · Pieces</a> › {E(n["th"])}</nav>',
                 f'<div class="phero">{self.stage(r, d, eager=True)}</div>',
                 f'<h1 class="ptitle"><span class="th">{E(n["th"])}</span> <span class="roman">{E(n["en"])}</span></h1>']
        k = self.by_kind.get(r.get("kind") or "")
        if k:
            lab = "ชนิด · kind" if (r.get("kind_how") or "").startswith("named") else "คล้าย · resembles"
            parts.append(f'<p class="like">{lab} <a href="../../kind/{E(k["id"])}/index.html"><span class="th">{E(k["names"]["th"])}</span> · {E(k["names"]["en"])}</a></p>'
                         f'<p class="th mute" lang="th" style="text-align:center">{E(k["text"].get("what_th", ""))}</p>'
                         f'<p class="mute" lang="en" style="text-align:center">{E(k["text"]["what_en"])}</p>')
        t = r.get("text") or {}
        if t.get("th"):
            parts.append(f'<p class="th" lang="th">{E(t["th"])}</p>')
        if t.get("en"):
            parts.append(f'<p lang="en">{E(t["en"])}</p>')
        photos = self.role(r, "photo")
        if photos:
            parts.append("<h2>Photographs · ภาพถ่าย</h2><div class=\"gallery\">" + "".join(
                f'<figure><a href="{E(self.src(m, d))}"><img src="{E(self.src(m, d))}" alt="{E(n["en"])}, photograph {j}" width="{m["width"]}" height="{m["height"]}" loading="lazy" decoding="async"></a>'
                f'<figcaption>{j} of {len(photos)}</figcaption></figure>' for j, m in enumerate(photos, 1)) + "</div>")
        cut = self.role(r, "cutout")
        rows = [("Photographed · ถ่ายเมื่อ", E(r.get("taken") or "—")),
                ("Photographer · ผู้ถ่าย", "Nan Peacock"),
                ("Licence · สัญญาอนุญาต", f'<a href="{E(self.license_url)}" rel="license">CC BY 4.0</a> — credit “Nan Peacock · wichaa.net”')]
        if cut:
            rows.append(("Cutout · ภาพตัดพื้น", f'<a href="{E(self.src(cut[0], d))}">transparent PNG, {cut[0]["width"]}×{cut[0]["height"]}</a>'))
        for ct in r.get("commons_files") or []:
            rows.append(("Wikimedia Commons", f'<a href="https://commons.wikimedia.org/wiki/{E(ct.replace(" ", "_"))}" rel="noopener">{E(ct)}</a>'))
        rows.append(("Data", f'<a href="../../api/piece/{E(r["id"])}.json" type="application/json">JSON</a>'))
        parts.append("<table>" + "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in rows) + "</table>")
        parts.append(f'<p class="cta"><a class="btn" href="../../identify/index.html">📷 <span class="th" lang="th">ถือชิ้นคล้ายกันอยู่? ถ่ายรูปเทียบ</span> · Holding one like it? Photograph it</a></p>')
        parts.append(f'<nav class="pnav"><a href="../{E(prev_r["id"])}/index.html">← {E(prev_r["names"]["th"])}</a>'
                     f'<a href="../{E(next_r["id"])}/index.html">{E(next_r["names"]["th"])} →</a></nav>')
        url = f"{self.site_url}/pieces/{r['id']}/"
        imgs = []
        for m in (cut + photos):
            imgs.append({"@type": "ImageObject", "contentUrl": self.abs(m), "url": url, "name": f"{n['th']} · {n['en']}",
                         "caption": n["en"], "creator": self.author, "creditText": "Nan Peacock · wichaa.net",
                         "copyrightNotice": "CC BY 4.0", "license": self.license_url, "acquireLicensePage": url,
                         "width": m["width"], "height": m["height"], "dateCreated": r.get("taken")})
        ld = [{"@context": "https://schema.org", "@type": "WebPage", "@id": url, "url": url, "name": f"{n['th']} · {n['en']}",
               "inLanguage": ["th", "en"], "license": self.license_url, "creator": self.author,
               "primaryImageOfPage": imgs[0] if imgs else None, "image": imgs,
               **({"about": {"@type": "DefinedTerm", "@id": f"{self.site_url}/kind/{k['id']}/", "name": k["names"]["th"], "alternateName": k["names"]["en"]}} if k else {}),
               "isPartOf": {"@type": "CollectionPage", "@id": f"{self.site_url}/pieces/"}},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "Amulet Essentials", "item": f"{self.site_url}/"},
                  {"@type": "ListItem", "position": 2, "name": "ชิ้นต่อชิ้น · Pieces", "item": f"{self.site_url}/pieces/"},
                  {"@type": "ListItem", "position": 3, "name": n["th"], "item": url}]}]
        extra = f"<style>{PIECE_CSS}</style>"
        cm = self.card_media(r)
        if cm:
            extra += (f'<meta property="og:image" content="{E(self.abs(cm))}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
                      f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{E(self.abs(cm))}">')
        desc = f"{n['en']} ({n['th']})" + (f", resembling {k['names']['en']} ({k['names']['th']})" if k else "") + ". Photographed by Nan Peacock; CC BY 4.0."
        return self.page(f"{n['th']} · {n['en']} — Pieces", "\n".join(parts), d, desc, ld, url, extra)

    # ---------------------------------------------------------------- hooks
    def kind_strip(self, kind_id: str, depth: int) -> str:
        rs = [r for r in self.recs if r.get("kind") == kind_id]
        if not rs:
            return ""
        return (f'<h2>Pieces · ชิ้นจริง <span class="count">({len(rs)})</span></h2>'
                f'<p class="mute" style="font-size:.9rem">Single pieces photographed here that resemble this kind.</p>'
                f'<style>{PIECE_CSS}</style><div class="pgrid">' + "".join(self.card(r, depth) for r in rs) + "</div>")

    def front_band(self) -> str:
        pick = [r for r in self.recs if self.role(r, "cutout_web")][:: max(1, len(self.recs) // 12)][:6]
        if not pick:
            return ""
        return (f'<style>{PIECE_CSS}</style><section aria-label="Pieces"><h2 style="border:0;margin-bottom:.1rem"><a href="pieces/index.html">'
                f'<span class="th">ชิ้นต่อชิ้น</span> · Pieces</a> <span class="count">({len(self.recs)})</span></h2>'
                '<div class="band">' + "".join(f'<a href="pieces/{E(r["id"])}/index.html">{self.stage(r, 0)}</a>' for r in pick) +
                '</div><p class="mute" style="font-size:.9rem;margin-top:.2rem">Amulets and sacred figures photographed one at a time, each with its own page.</p></section>')

    def sitemap_xml(self) -> str:
        out = [f"<url><loc>{E(self.site_url)}/pieces/</loc></url>"]
        for r in self.recs:
            n = r["names"]
            ims = "".join(f"<image:image><image:loc>{E(self.abs(m))}</image:loc><image:caption>{E(n['th'])} · {E(n['en'])}</image:caption>"
                          f"<image:title>{E(n['th'])} {E(n['en'])}</image:title><image:license>{E(self.license_url)}</image:license></image:image>"
                          for m in r.get("media", []) if m["role"] in ("cutout", "photo"))
            out.append(f"<url><loc>{E(self.site_url)}/pieces/{E(r['id'])}/</loc>" + (f"<lastmod>{E(r['taken'])}</lastmod>" if r.get("taken") else "") + ims + "</url>")
        return "".join(out)

    def llms_lines(self) -> list[str]:
        lines = ["", "## Pieces", f"- [ชิ้นต่อชิ้น · Pieces]({self.site_url}/pieces/): {len(self.recs)} single amulets and sacred figures, photographed one by one by Nan Peacock (CC BY 4.0); cutouts on transparent ground. Data: {self.site_url}/api/pieces.json"]
        for r in self.recs:
            k = self.by_kind.get(r.get("kind") or "")
            lines.append(f"- [{r['names']['th']} · {r['names']['en']}]({self.site_url}/pieces/{r['id']}/)" + (f" — resembles {k['names']['en']}" if k else ""))
        return lines

    def api(self) -> dict:
        def pub(r):
            o = {k: v for k, v in r.items() if k not in ("photos", "hero")}
            o["url"] = f"{self.site_url}/pieces/{r['id']}/"
            o["media"] = [{**m, "url": self.abs(m)} for m in r.get("media", [])]
            o["license"] = self.license_url
            return o
        return {"count": len(self.recs), "license": self.license_url, "pieces": [pub(r) for r in self.recs]}

    # ---------------------------------------------------------------- write
    def render(self, site: Path) -> int:
        if not self.image_base:
            for m in self.all_media():
                src = self.own / m["file"]
                dst = site / "images" / "own" / m["file"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
        (site / "pieces").mkdir(parents=True, exist_ok=True)
        (site / "pieces" / "index.html").write_text(self.index_page(), encoding="utf-8")
        (site / "api" / "piece").mkdir(parents=True, exist_ok=True)
        api = self.api()
        (site / "api" / "pieces.json").write_text(json.dumps(api, ensure_ascii=False, indent=1), encoding="utf-8")
        for r, pr in zip(self.recs, api["pieces"]):
            pd = site / "pieces" / r["id"]
            pd.mkdir(parents=True, exist_ok=True)
            (pd / "index.html").write_text(self.piece_page(r), encoding="utf-8")
            (site / "api" / "piece" / f"{r['id']}.json").write_text(json.dumps(pr, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(self.recs)
