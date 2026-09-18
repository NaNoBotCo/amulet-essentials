#!/usr/bin/env python3
"""value_page.py — /value: how cash value is assigned to amulets, as infographics.

Reads data/analysis/value_factors.json (the research deliverable) and draws, inline SVG,
no libraries. One hue throughout (magnitude = darker), confidence written as text, every
chart with a table twin (bots and screen readers read the table). Called by site.py.
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

import price_charts

E = html.escape


def thb(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v >= 1e9:
        return f"฿{v/1e9:g}bn"
    if v >= 1e6:
        return f"฿{v/1e6:g}M"
    if v >= 1e3:
        return f"฿{v/1e3:g}k"
    return f"฿{v:g}"


def mult(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{v:,.0f}×" if v >= 10 else f"{v:g}×"


def bars(rows, value_key, label, unit="", n_key=None, sub=None, max_v=None, width=760, fmt=None) -> str:
    rows = [r for r in rows if r.get(value_key) not in (None, "")]
    if not rows:
        return '<p class="mute">no data</p>'
    vals = [float(r[value_key]) for r in rows]
    max_v = max_v or max(vals) or 1.0
    lh, gap, left = 28, 8, 270
    h = 12 + len(rows) * (lh + gap)
    out = [f'<svg class="viz" viewBox="0 0 {width} {h}" role="img" aria-label="bar chart">']
    for i, (r, v) in enumerate(zip(rows, vals)):
        y = 6 + i * (lh + gap)
        w = max(3, (width - left - 110) * v / max_v)
        shade = 0.5 + 0.5 * (v / max_v)
        lab = label(r)
        s = f' <tspan class="mute" font-size="11">{E(str(sub(r)))}</tspan>' if sub and sub(r) else ""
        n = f' <tspan class="mute" font-size="11">n={r[n_key]}</tspan>' if n_key and r.get(n_key) is not None else ""
        out.append(f'<text x="{left - 10}" y="{y + 19}" text-anchor="end" font-size="13" class="ink">{E(lab[:36])}{s}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{lh}" rx="4" class="bar" style="opacity:{shade:.2f}"/>')
        out.append(f'<text x="{left + w + 8:.1f}" y="{y + 19}" font-size="13" class="ink">{E((fmt or (thb if unit == "฿" else (lambda x: f"{x:g}")))(v))}{n}</text>')
    out.append("</svg>")
    return "".join(out)


def log_ranges(rows, lo_key, hi_key, label, width=760, unit="฿") -> str:
    rows = [r for r in rows if r.get(lo_key) and r.get(hi_key)]
    if not rows:
        return '<p class="mute">no data</p>'
    lo = min(max(1.0, float(r[lo_key])) for r in rows)
    hi = max(float(r[hi_key]) for r in rows)
    L, R = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    left, right, lh, gap = 270, 120, 26, 10
    h = 36 + len(rows) * (lh + gap)
    span = width - left - right
    f = thb if unit == "฿" else mult

    def x(v):
        return left + span * (math.log10(max(1.0, float(v))) - L) / max(1e-9, (R - L))
    out = [f'<svg class="viz" viewBox="0 0 {width} {h}" role="img" aria-label="range chart, log scale">']
    for p in range(L, R + 1):
        xx = x(10 ** p)
        out.append(f'<line x1="{xx:.1f}" y1="6" x2="{xx:.1f}" y2="{h - 26}" class="grid"/><text x="{xx:.1f}" y="{h - 10}" text-anchor="middle" font-size="11" class="mute">{E(f(10 ** p))}</text>')
    for i, r in enumerate(rows):
        y = 8 + i * (lh + gap)
        x1, x2 = x(r[lo_key]), x(r[hi_key])
        out.append(f'<text x="{left - 10}" y="{y + 18}" text-anchor="end" font-size="13" class="ink">{E(label(r)[:38])}</text>')
        out.append(f'<rect x="{x1:.1f}" y="{y}" width="{max(5, x2 - x1):.1f}" height="{lh}" rx="4" class="bar"/>')
        out.append(f'<text x="{x2 + 8:.1f}" y="{y + 18}" font-size="12" class="ink">{E(f(r[lo_key]))}–{E(f(r[hi_key]))}</text>')
    out.append("</svg>")
    return "".join(out)


def table(rows, cols) -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{E(h)}</th>" for _, h in cols)
    body = "".join("<tr>" + "".join(f"<td>{E(str(r.get(k, '')) if r.get(k) is not None else '')}</td>" for k, _ in cols) + "</tr>" for r in rows)
    return f'<details><summary>Table · ตาราง</summary><table><tr>{head}</tr>{body}</table></details>'


def lbl(r):
    """Thai term first; when the pair would not fit a chart label, the Thai alone, trimmed at a
    bracket or slash so a truncated label still reads as a term, not a fragment."""
    th, en = str(r.get("label_th", "") or ""), str(r.get("label_en", "") or "")
    both = f"{th} · {en}".strip(" ·")
    if len(both) <= 34:
        return both or r.get("label", "")
    short = re.split(r"\s*[(/]", th)[0].strip() if th else en
    return (f"{short} · {en}" if len(f"{short} · {en}") <= 34 else short)[:34] or r.get("label", "")


def render(vf: dict, ps: dict | None = None) -> str:
    cr = vf.get("chart_ready", {}) or {}
    parts = ['<h1>What sets the price · อะไรกำหนดราคา <span class="roman">how cash value is assigned to amulets, in real life</span></h1>']
    ans = vf.get("answer_10_lines")
    if ans:
        lines = ans if isinstance(ans, list) else str(ans).split("\n")
        lines = [re.sub(r"^\s*\d+[.)]\s*", "", str(l)) for l in lines if str(l).strip()]
        parts.append('<div class="card"><ol style="margin:.2rem 0 .2rem 1.2rem;padding:0">' + "".join(f"<li>{E(l)}</li>" for l in lines) + "</ol></div>")

    fw = cr.get("factor_weights") or []
    parts.append('<h2>The factors, ranked · ปัจจัย เรียงตามน้ำหนัก</h2><p class="mute">Bar = weight in the trade, 0–100, as the research assigned it. The confidence word says how sure the evidence is.</p>')
    parts.append(bars(fw, "weight", lbl, max_v=100, sub=lambda r: r.get("confidence")))
    parts.append(table(fw, [("rank", "#"), ("label_th", "ปัจจัย"), ("label_en", "factor"), ("weight", "weight"), ("confidence", "confidence"), ("basis", "basis")]))

    parts.append('<h2>How much each factor can move a price · ช่วงตัวคูณ</h2><p class="mute">Log scale. The low and high multiplier the sources give for the same object with and without the factor.</p>')
    parts.append(log_ranges([r for r in fw if r.get("multiplier_low") and r.get("multiplier_high")], "multiplier_low", "multiplier_high", lbl, unit="×"))
    parts.append(table(fw, [("label_en", "factor"), ("multiplier_low", "low ×"), ("multiplier_high", "high ×"), ("evidence_count", "evidence")]))

    parts.append('<h3>Weight against reach · น้ำหนัก เทียบ ตัวคูณ</h3>')
    parts.append(price_charts.factor_scatter(fw))

    facts = sorted(vf.get("factors", []), key=lambda f: int(f.get("rank", 99)))
    if facts:
        parts.append("<h2>Each factor · ทีละปัจจัย</h2><table>")
        for f in facts:
            ev = "".join(f'<br><a href="{E(e.get("url",""))}" rel="noopener">{E(str(e.get("title","source"))[:110])}</a>' for e in (f.get("evidence") or [])[:4] if isinstance(e, dict))
            mb = ", ".join(f.get("measured_by") or []) if isinstance(f.get("measured_by"), list) else str(f.get("measured_by", ""))
            parts.append(f'<tr><th>{E(str(f.get("rank","")))}. <span class="th">{E(f.get("th",""))}</span><br><span class="mute">{E(f.get("en",""))}</span><br><span class="chip">{E(str(f.get("confidence","")))}</span></th>'
                         f'<td><b>Mechanism:</b> {E(f.get("mechanism",""))}<br><b>Measured by:</b> {E(mb)}<br><b>Price effect:</b> {E(f.get("price_effect",""))}<span class="mute">{ev}</span></td></tr>')
        parts.append("</table>")

    tiers = cr.get("tier_ladder_thb") or []
    parts.append('<h2>The tiers of the market · ชั้นของตลาด</h2><p class="mute">Log scale in baht. The same shelf runs from pocket change to a house deposit; the tier decides which rules apply.</p>')
    parts.append(log_ranges(tiers, "low", "high", lbl))
    tt = vf.get("tiers") or []
    parts.append(table([{**t, "governed_by": ", ".join(t.get("governed_by") or [])} for t in tt], [("th", "tier"), ("en", ""), ("thb_low", "low ฿"), ("thb_high", "high ฿"), ("thb_median", "median"), ("governed_by", "governed by")]))

    ml = cr.get("material_ladder_same_die") or []
    if ml:
        parts.append('<h2>Metal tier, same die · เนื้อบน กลาง ล่าง (พิมพ์เดียวกัน)</h2><p class="mute">The same monk, the same year, the same mould, four bodies. Ratio to the copper piece. Gold is a rank marker, not bullion: the metal in a ฿10M piece is worth about ฿50k.</p>')
        parts.append("<h3>Luang Pho Koon 2519 · ราคาซื้อขาย</h3>" + bars(ml, "ratio_to_copper_koon", lbl, fmt=mult))
        parts.append("<h3>Pantip ladder · อีกแหล่ง</h3>" + bars(ml, "ratio_to_copper_pantip", lbl, fmt=mult))
        parts.append(table(ml, [("label_th", "เนื้อ"), ("label_en", "metal"), ("lp_koon_2519_thb", "LP Koon 2519 ฿"), ("ratio_to_copper_koon", "× copper"), ("pantip_thb", "Pantip ฿"), ("ratio_to_copper_pantip", "× copper")]))

    rec = cr.get("record_prices_thb") or []
    if rec:
        parts.append('<h2>Record prices · ราคาสถิติ</h2><p class="mute">Reported asking or sale ranges for named pieces. Log scale.</p>')
        parts.append(log_ranges(rec, "low", "high", lambda r: r.get("label", "")))
        parts.append(table(rec, [("label", "piece"), ("low", "low ฿"), ("high", "high ฿"), ("source", "source")]))

    ms = cr.get("market_size_thb") or []
    if ms:
        parts.append('<h2>Size of the market · ขนาดตลาด</h2>')
        parts.append(bars(ms, "value", lambda r: r.get("label", ""), unit="฿"))
        parts.append(table(ms, [("label", "estimate"), ("value", "฿ / year"), ("source", "source")]))

    if ps:
        o = ps["overall"]
        parts.append(f'<h2>What our own corpus shows · จากคลังของเรา</h2>'
                     f'<p class="mute">{o["n"]:,} priced listings from Lazada Thailand, all in baht. Every figure below is a '
                     f'match on a listing TITLE: it says what sellers ask for objects they describe with that word, never what a '
                     f'piece is worth. This is the retail tier — the dealer and sian markets do not list here and are invisible in '
                     f'these numbers.</p>')
        parts.append("<h3>The shape of the retail market · การกระจายราคา</h3>")
        parts.append(price_charts.distribution(o))
        parts.append("<h3>Common or dear? · จำนวนประกาศ เทียบ ราคากลาง</h3>"
                     '<p class="mute">One point per kind: how many listings carry its term, against what they ask. Both axes '
                     'logarithmic. Colour and shape carry the class axis\'s own question — does anything live in it.</p>')
        parts.append(price_charts.scatter_kinds(ps["kinds"], o))
        parts.append("<h3>Where each kind sits · ช่วงราคาของแต่ละชนิด</h3>")
        parts.append(price_charts.iqr_bands(ps["kinds"]))
        parts.append("<h3>By class — the finding · ตามหมวด</h3>"
                     '<p class="mute">At this tier the classes that house a resident ask MORE than the Buddha amulets. That is the '
                     'reverse of the expert market, where a พระเครื่อง carries every record price in the section above. Two different '
                     'markets wearing one word.</p>')
        parts.append(price_charts.classes_chart(ps["classes"], o))
        parts.append("<h3>What a word is worth · คำที่ขึ้นราคา</h3>"
                     '<p class="mute">Median of listings whose title carries the word, against the corpus median. These are claims a '
                     'seller types, not facts anyone checked — which is the point: at retail the WORD is what moves the price.</p>')
        parts.append(price_charts.keyword_ladder(ps["keywords"], o))
    cf = vf.get("corpus_findings") or []
    if cf:
        parts.append("<h3>Notes on the corpus</h3><ul>" + "".join(f"<li>{E(str(x))}</li>" for x in cf) + "</ul>")

    if vf.get("myths"):
        parts.append("<h2>What does not set the price · ที่ไม่ใช่</h2><table>")
        for m in vf["myths"]:
            if isinstance(m, dict):
                parts.append(f'<tr><th><span class="th">{E(m.get("th",""))}</span><br><span class="mute">{E(m.get("en",""))}</span></th><td>{E(m.get("why",""))} <span class="mute">{E(str(m.get("source","")))}</span></td></tr>')
        parts.append("</table>")
    if vf.get("sources"):
        parts.append("<h2>Sources</h2><ul>" + "".join(f'<li><a href="{E(s.get("url",""))}" rel="noopener">{E(s.get("title", s.get("url","")))}</a> <span class="mute">{E(str(s.get("lang","")))} · {E(str(s.get("kind","")))}</span></li>' if isinstance(s, dict) else f"<li>{E(str(s))}</li>" for s in vf["sources"]) + "</ul>")
    fees = cr.get("certificate_fees_thb") or []
    if fees:
        parts.append("<p class=\"mute\">Certificate fees: " + " · ".join(f"{E(str(f.get('label','')))} ฿{E(str(f.get('fee','')))}" for f in fees) + "</p>")
    parts.append(f'<p class="bots">This analysis as data: <a href="../api/value_factors.json">value_factors.json</a> · built {E(str(vf.get("built","")))}</p>')
    return "\n".join(parts)


VIZ_CSS = price_charts.CSS + """
.viz{width:100%;height:auto;max-width:760px;display:block;margin:.5rem 0 .5rem}.viz .bar{fill:var(--teal)}.viz .ink{fill:var(--ink)}.viz .mute{fill:var(--mute)}.viz .grid{stroke:var(--line);stroke-width:1}
details summary{cursor:pointer;color:var(--mute);font-size:.9rem}details table{font-size:.85rem}
"""


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "analysis" / "value_factors.json"
    print(render(json.loads(p.read_text(encoding="utf-8")))[:1500])
