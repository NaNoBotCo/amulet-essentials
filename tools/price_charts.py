#!/usr/bin/env python3
"""price_charts.py — the corpus's own price data, drawn. Inline SVG, no libraries.

Charts here read data/analysis/price_stats.json (built by tools/price_stats.py from the
15,295 priced Lazada Thailand listings) rather than the research JSON: this is what OUR
data says, as against what the trade says.

Colour rules followed: magnitude charts are ONE hue, darker = more. The scatter is the only
categorical encoding and it carries exactly two series — nobody home vs a resident — which
is the archive's own thesis, drawn from the vault class axis. Those two hues are the
reference palette's validated slots 1 and 2 (blue / orange), which pass the lightness,
chroma, CVD-separation, normal-vision and contrast checks against both page surfaces; they
are backed by a second encoding (circle vs diamond) and a legend, so identity is never
colour alone. Every chart has a table twin and per-mark <title> tooltips.
"""
from __future__ import annotations

import html
import math

E = html.escape


def thb(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v >= 1e6:
        return f"฿{v/1e6:g}M"
    if v >= 1e3:
        return f"฿{v/1e3:g}k"
    return f"฿{v:g}"


def table(rows, cols, label="Table · ตาราง") -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{E(h)}</th>" for _, h in cols)
    body = "".join("<tr>" + "".join(f"<td>{E('' if r.get(k) is None else str(r.get(k)))}</td>" for k, _ in cols) + "</tr>" for r in rows)
    return f'<details><summary>{E(label)}</summary><table><tr>{head}</tr>{body}</table></details>'


# ---------------------------------------------------------------- distribution

def distribution(overall: dict, width=760) -> str:
    """The shape of the market: how many listings sit in each decade of price."""
    hist = overall.get("histogram_by_decade") or []
    if not hist:
        return ""
    H, top, bot, left, right = 300, 24, 56, 64, 20
    plot_w, plot_h = width - left - right, H - top - bot
    max_n = max(h["n"] for h in hist)
    bw = plot_w / len(hist)
    out = [f'<svg class="viz" viewBox="0 0 {width} {H}" role="img" aria-label="price distribution by decade">']
    for frac in (0, .5, 1):
        y = top + plot_h * (1 - frac)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" class="mute">{int(max_n*frac):,}</text>')
    for i, h in enumerate(hist):
        x = left + i * bw
        bh = plot_h * h["n"] / max_n
        y = top + plot_h - bh
        shade = 0.45 + 0.55 * (h["n"] / max_n)
        out.append(f'<rect x="{x+3:.1f}" y="{y:.1f}" width="{bw-6:.1f}" height="{max(2,bh):.1f}" rx="4" class="bar" style="opacity:{shade:.2f}">'
                   f'<title>{E(h["label"])}: {h["n"]:,} listings ({h["share"]}%)</title></rect>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" text-anchor="middle" font-size="11" class="ink">{h["n"]:,}</text>')
        tick = f'{thb(h["low"])}–{thb(h["high"]).lstrip("฿")}'
        out.append(f'<text x="{x+bw/2:.1f}" y="{H-36}" text-anchor="middle" font-size="10" class="mute">{E(tick)}</text>')
    out.append(f'<text x="{left+plot_w/2:.0f}" y="{H-12}" text-anchor="middle" font-size="11" class="mute">price, baht (each step is ten times the last)</text>')
    out.append("</svg>")
    marks = (f'<p class="mute">median <b class="ink">{thb(overall["median"])}</b> · '
             f'half of everything sells between {thb(overall["p25"])} and {thb(overall["p75"])} · '
             f'nine in ten under {thb(overall["p90"])} · dearest listing {thb(overall["max"])}, '
             f'{overall["max"]/overall["median"]:,.0f}× the median.</p>')
    return "".join(out) + marks + table(hist, [("label", "band"), ("n", "listings"), ("share", "% of corpus")])


# -------------------------------------------------------------------- scatter

RESIDENT_SERIES = [
    ("none", "nobody home · ไม่มีผู้อยู่", "s1", "circle"),
    ("resident", "someone lives in it · มีผู้อยู่", "s2", "diamond"),
]


def _mark(x, y, kind, cls, r=6) -> str:
    if kind == "diamond":
        return (f'<polygon points="{x:.1f},{y-r-1:.1f} {x+r+1:.1f},{y:.1f} {x:.1f},{y+r+1:.1f} {x-r-1:.1f},{y:.1f}" '
                f'class="{cls} mark"/>')
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" class="{cls} mark"/>'


def scatter_kinds(kinds: list[dict], overall: dict, width=760) -> str:
    """One point per kind: how many listings carry its term (x) against what they ask (y).

    Both axes are logarithmic because both span three orders of magnitude. The two series
    are the class axis's own question — does anything live in it — so the chart answers a
    question a price table cannot: at this tier, are spirit-bearing objects dearer?
    """
    pts = [k for k in kinds if k.get("n") and k.get("median")]
    if len(pts) < 4:
        return ""
    H, top, bot, left, right = 430, 20, 60, 68, 130
    pw, ph = width - left - right, H - top - bot
    xs = [k["n"] for k in pts]
    ys = [k["median"] for k in pts]
    XL, XR = 0, math.ceil(math.log10(max(xs)))
    YL, YR = math.floor(math.log10(min(ys))), math.ceil(math.log10(max(ys)))

    def X(v):
        return left + pw * (math.log10(max(1, v)) - XL) / max(1e-9, XR - XL)

    def Y(v):
        return top + ph - ph * (math.log10(max(1, v)) - YL) / max(1e-9, YR - YL)
    out = [f'<svg class="viz" viewBox="0 0 {width} {H}" role="img" '
           f'aria-label="scatter plot: listings against median price, one point per kind of amulet, logarithmic on both axes">']
    for p in range(XL, XR + 1):
        x = X(10 ** p)
        out.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+ph}" class="grid"/>'
                   f'<text x="{x:.1f}" y="{top+ph+18}" text-anchor="middle" font-size="11" class="mute">{10**p:,}</text>')
    for p in range(YL, YR + 1):
        y = Y(10 ** p)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+pw:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" class="mute">{E(thb(10**p))}</text>')
    med = overall["median"]
    ym = Y(med)
    out.append(f'<line x1="{left}" y1="{ym:.1f}" x2="{left+pw:.1f}" y2="{ym:.1f}" class="ref"/>'
               f'<text x="{left+pw-4:.1f}" y="{ym-6:.1f}" text-anchor="end" font-size="11" class="mute">corpus median {E(thb(med))}</text>')
    # marks, dearest last so they sit on top
    for k in sorted(pts, key=lambda k: k["median"]):
        cls = "s2" if (k.get("resident") and k["resident"] != "none") else "s1"
        shape = "diamond" if cls == "s2" else "circle"
        out.append(f'<g><title>{E(k["label_th"])} · {E(k["label_en"])} — {k["n"]:,} listings, median {E(thb(k["median"]))}, '
                   f'half between {E(thb(k["p25"]))} and {E(thb(k["p75"]))} · {E(str(k.get("cls_th") or "unplaced"))}</title>'
                   f'{_mark(X(k["n"]), Y(k["median"]), shape, cls)}</g>')
    # direct labels: the four corners of the argument, never every point
    label_ids = set()
    label_ids.add(max(pts, key=lambda k: k["n"])["id"])
    label_ids.add(max(pts, key=lambda k: k["median"])["id"])
    label_ids.add(min(pts, key=lambda k: k["median"])["id"])
    dear_common = max((k for k in pts if k["n"] >= 100), key=lambda k: k["median"], default=None)
    if dear_common:
        label_ids.add(dear_common["id"])
    for k in pts:
        if k["id"] not in label_ids:
            continue
        x, y = X(k["n"]), Y(k["median"])
        anchor = "end" if x > left + pw * 0.7 else "start"
        dx = -12 if anchor == "end" else 12
        out.append(f'<text x="{x+dx:.1f}" y="{y+4:.1f}" text-anchor="{anchor}" font-size="12" class="ink">{E(k["label_th"])}</text>')
    out.append(f'<text x="{left+pw/2:.0f}" y="{H-24}" text-anchor="middle" font-size="11" class="mute">listings carrying the term (log)</text>')
    ly = top + 8
    for i, (_, lab, cls, shape) in enumerate(RESIDENT_SERIES):
        yy = ly + i * 22
        out.append(_mark(left + pw + 22, yy, shape, cls) + f'<text x="{left+pw+34}" y="{yy+4}" font-size="11" class="ink">{E(lab.split(" · ")[0])}</text>')
    out.append("</svg>")
    rows = sorted(pts, key=lambda k: -k["median"])
    return "".join(out) + table(rows, [("label_th", "kind"), ("label_en", ""), ("n", "listings"), ("median", "median ฿"),
                                       ("p25", "p25"), ("p75", "p75"), ("cls_th", "class"), ("resident", "resident")])


# ------------------------------------------------------------------- IQR band

def iqr_bands(kinds: list[dict], n_min=40, limit=28, width=760) -> str:
    """Where each well-attested kind actually sits: the middle half of its asking prices."""
    rows = sorted([k for k in kinds if k["n"] >= n_min], key=lambda k: -k["median"])[:limit]
    if not rows:
        return ""
    lh, gap, left, right = 22, 7, 240, 96
    H = 34 + len(rows) * (lh + gap)
    pw = width - left - right
    lo = min(k["p25"] for k in rows)
    hi = max(k["p90"] for k in rows)
    L, R = math.floor(math.log10(max(1, lo))), math.ceil(math.log10(hi))

    def X(v):
        return left + pw * (math.log10(max(1, v)) - L) / max(1e-9, R - L)
    out = [f'<svg class="viz" viewBox="0 0 {width} {H}" role="img" aria-label="price band per kind, quartiles, log scale">']
    for p in range(L, R + 1):
        x = X(10 ** p)
        out.append(f'<line x1="{x:.1f}" y1="6" x2="{x:.1f}" y2="{H-24}" class="grid"/>'
                   f'<text x="{x:.1f}" y="{H-8}" text-anchor="middle" font-size="11" class="mute">{E(thb(10**p))}</text>')
    for i, k in enumerate(rows):
        y = 8 + i * (lh + gap)
        x1, x2, xm, x9 = X(k["p25"]), X(k["p75"]), X(k["median"]), X(k["p90"])
        out.append(f'<g><title>{E(k["label_th"])} · {E(k["label_en"])} — {k["n"]:,} listings · median {E(thb(k["median"]))} · '
                   f'p25 {E(thb(k["p25"]))} · p75 {E(thb(k["p75"]))} · p90 {E(thb(k["p90"]))}</title>'
                   f'<line x1="{x2:.1f}" y1="{y+lh/2:.1f}" x2="{x9:.1f}" y2="{y+lh/2:.1f}" class="whisker"/>'
                   f'<rect x="{x1:.1f}" y="{y}" width="{max(3,x2-x1):.1f}" height="{lh}" rx="4" class="bar" style="opacity:.55"/>'
                   f'<rect x="{xm-1.5:.1f}" y="{y-2}" width="3" height="{lh+4}" rx="1.5" class="median"/></g>')
        out.append(f'<text x="{left-10}" y="{y+15}" text-anchor="end" font-size="12" class="ink">{E(k["label_th"][:20])} '
                   f'<tspan class="mute" font-size="10">n={k["n"]}</tspan></text>')
        out.append(f'<text x="{x9+8:.1f}" y="{y+15}" font-size="11" class="ink">{E(thb(k["median"]))}</text>')
    out.append("</svg>")
    return ("".join(out)
            + '<p class="mute">Bar = the middle half of asking prices (p25–p75); the line inside it is the median; '
              'the whisker runs to the ninth decile. Kinds with at least 40 listings, dearest first.</p>'
            + table(rows, [("label_th", "kind"), ("n", "listings"), ("p25", "p25"), ("median", "median"), ("p75", "p75"), ("p90", "p90")]))


# --------------------------------------------------------------------- classes

def classes_chart(classes: list[dict], overall: dict, width=760) -> str:
    """The finding: at retail, the classes that house a resident ask MORE than the Buddha
    amulets — the reverse of the expert tier, where a phra khrueang carries the record prices."""
    rows = [c for c in classes if c.get("kinds")]
    if not rows:
        return ""
    lh, gap, left = 30, 10, 250
    H = 40 + len(rows) * (lh + gap)
    max_v = max(c["median_of_kind_medians"] for c in rows)
    pw = width - left - 130
    out = [f'<svg class="viz" viewBox="0 0 {width} {H}" role="img" aria-label="median price by class of object">']
    xm = left + pw * overall["median"] / max_v
    out.append(f'<line x1="{xm:.1f}" y1="4" x2="{xm:.1f}" y2="{H-26}" class="ref"/>'
               f'<text x="{xm+6:.1f}" y="{H-10}" font-size="11" class="mute">corpus median {E(thb(overall["median"]))}</text>')
    for i, c in enumerate(rows):
        y = 6 + i * (lh + gap)
        v = c["median_of_kind_medians"]
        w = max(3, pw * v / max_v)
        res = c.get("resident")
        cls = "s2" if res and res != "none" else "s1"
        out.append(f'<g><title>{E(c["label_th"])} — {c["kinds"]} kinds, {c["listings"]:,} listings · median of kind medians '
                   f'{E(thb(v))} · pooled median {E(thb(c["median_pooled"]))} · resident: {E(str(res))}</title>'
                   f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{lh}" rx="4" class="{cls}fill"/></g>')
        out.append(f'<text x="{left-10}" y="{y+20}" text-anchor="end" font-size="13" class="ink">{E(c["label_th"])} '
                   f'<tspan class="mute" font-size="10">{E(str(res or "—"))}</tspan></text>')
        out.append(f'<text x="{left+w+8:.1f}" y="{y+20}" font-size="12" class="ink">{E(thb(v))} '
                   f'<tspan class="mute" font-size="10">{c["kinds"]} kinds · n={c["listings"]:,}</tspan></text>')
    out.append("</svg>")
    return "".join(out) + table(rows, [("label_th", "class"), ("resident", "resident"), ("kinds", "kinds"),
                                       ("listings", "listings"), ("median_of_kind_medians", "median of kind medians"),
                                       ("median_pooled", "pooled median")])


# -------------------------------------------------------------------- keywords

def keyword_ladder(keywords: list[dict], overall: dict, width=760) -> str:
    """What a WORD is worth: the median of listings whose title carries it, against ฿129."""
    rows = keywords[:16]
    if not rows:
        return ""
    lh, gap, left = 26, 8, 250
    H = 34 + len(rows) * (lh + gap)
    pw = width - left - 150
    max_r = max(k["ratio_to_all"] for k in rows)
    x1 = left + pw / max_r
    out = [f'<svg class="viz" viewBox="0 0 {width} {H}" role="img" aria-label="price lift by keyword in the listing title">']
    out.append(f'<line x1="{x1:.1f}" y1="4" x2="{x1:.1f}" y2="{H-24}" class="ref"/>'
               f'<text x="{x1+6:.1f}" y="{H-8}" font-size="11" class="mute">1.0× — the corpus median, {E(thb(overall["median"]))}</text>')
    for i, k in enumerate(rows):
        y = 6 + i * (lh + gap)
        w = max(3, pw * k["ratio_to_all"] / max_r)
        shade = 0.45 + 0.55 * (k["ratio_to_all"] / max_r)
        out.append(f'<g><title>{E(k["label_th"])} · {E(k["label_en"])} — {k["n"]:,} listings, median {E(thb(k["median"]))} '
                   f'({k["ratio_to_all"]}× the corpus median)</title>'
                   f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{lh}" rx="4" class="bar" style="opacity:{shade:.2f}"/></g>')
        out.append(f'<text x="{left-10}" y="{y+18}" text-anchor="end" font-size="12" class="ink">{E(k["label_th"])} '
                   f'<tspan class="mute" font-size="10">{E(k["label_en"][:22])}</tspan></text>')
        out.append(f'<text x="{left+w+8:.1f}" y="{y+18}" font-size="12" class="ink">{k["ratio_to_all"]}× '
                   f'<tspan class="mute" font-size="10">{E(thb(k["median"]))} · n={k["n"]:,}</tspan></text>')
    out.append("</svg>")
    return "".join(out) + table(rows, [("label_th", "word"), ("label_en", ""), ("n", "listings"),
                                       ("median", "median ฿"), ("ratio_to_all", "× corpus median")])


# --------------------------------------------------------------- factor scatter

def factor_scatter(fw: list[dict], width=760) -> str:
    """The trade's own factors: how much weight each carries against how far it can move
    a price. Genuineness is an outlier."""
    pts = [f for f in fw if f.get("weight") and f.get("multiplier_high")]
    if len(pts) < 4:
        return ""
    H, top, bot, left, right = 380, 20, 56, 78, 40
    pw, ph = width - left - right, H - top - bot
    YL, YR = 0, math.ceil(math.log10(max(f["multiplier_high"] for f in pts)))

    def X(v):
        return left + pw * (v / 100)

    def Y(v):
        return top + ph - ph * (math.log10(max(1, v)) - YL) / max(1e-9, YR - YL)
    out = [f'<svg class="viz" viewBox="0 0 {width} {H}" role="img" aria-label="scatter: factor weight against how far it moves a price">']
    for p in range(YL, YR + 1):
        y = Y(10 ** p)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+pw:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" class="mute">{10**p:,}×</text>')
    for v in (0, 25, 50, 75, 100):
        x = X(v)
        out.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+ph}" class="grid"/>'
                   f'<text x="{x:.1f}" y="{top+ph+18}" text-anchor="middle" font-size="11" class="mute">{v}</text>')
    for f in sorted(pts, key=lambda f: f["weight"]):
        x, y = X(f["weight"]), Y(f["multiplier_high"])
        lo = Y(f.get("multiplier_low") or f["multiplier_high"])
        out.append(f'<g><title>{E(f.get("label_th",""))} · {E(f.get("label_en",""))} — weight {f["weight"]}, '
                   f'moves a price {f.get("multiplier_low","?")}× to {f["multiplier_high"]:,}× · {E(str(f.get("confidence","")))} confidence</title>'
                   f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{lo:.1f}" class="whisker"/>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" class="s1 mark"/></g>')
        out.append(f'<text x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle" font-size="11" class="ink">{E(str(f.get("label_en",""))[:16])}</text>')
    out.append(f'<text x="{left+pw/2:.0f}" y="{H-16}" text-anchor="middle" font-size="11" class="mute">weight in the trade (0–100)</text>')
    out.append("</svg>")
    return ("".join(out)
            + '<p class="mute">The dot is the top of the range a factor can move a price; the stalk drops to the bottom of it. '
              'Vertical axis is logarithmic.</p>')


CSS = """
.viz .s1,.viz .s1fill{fill:#2a78d6}.viz .s2,.viz .s2fill{fill:#eb6834}
.viz .mark{stroke:var(--bg);stroke-width:2}
.viz .ref{stroke:var(--mute);stroke-width:1.5;stroke-dasharray:5 4;opacity:.7}
.viz .whisker{stroke:var(--mute);stroke-width:2;opacity:.55}
.viz .median{fill:var(--ink)}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .viz .s1,:root:not([data-theme="light"]) .viz .s1fill{fill:#3987e5}
:root:not([data-theme="light"]) .viz .s2,:root:not([data-theme="light"]) .viz .s2fill{fill:#d95926}}
:root[data-theme="dark"] .viz .s1,:root[data-theme="dark"] .viz .s1fill{fill:#3987e5}
:root[data-theme="dark"] .viz .s2,:root[data-theme="dark"] .viz .s2fill{fill:#d95926}
"""
