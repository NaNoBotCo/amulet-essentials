#!/usr/bin/env python3
"""vision.py — "I photographed it": which kind does this picture look like?

A sian's first move with an unknown piece is to photograph it and run the photo through a
reverse-image search. This is that, over OUR labelled image bank, answering with kinds and
their records instead of shopping links.

How: CLIP ViT-B/32 (ONNX via fastembed, runs offline in .venv) embeds every
harvested image; a query photo is embedded the same way and compared. Per kind we take the
best-matching picture. Kinds with no picture yet fall back to a TEXT prototype ("a photo of
a <kind>, <what it is>") embedded by the matching CLIP text tower, marked `via: text`, so a
kind stays findable even when nobody has photographed it under a free licence.

    .venv/bin/python tools/vision.py --build              # build/image_vectors.json (resumable)
    .venv/bin/python tools/vision.py photo.jpg [-n 5]     # identify
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, IMAGES, jdump, jload  # noqa: E402

IMG_MODEL = "Qdrant/clip-ViT-B-32-vision"
TXT_MODEL = "Qdrant/clip-ViT-B-32-text"
OUT = BUILD / "image_vectors.json"


def _unit(v):
    v = [float(x) for x in v]          # numpy float32 is not JSON-serialisable; plain floats are
    n = float(sum(x * x for x in v)) ** 0.5 or 1.0
    return [round(x / n, 6) for x in v]


class Vision:
    def __init__(self):
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        from fastembed import ImageEmbedding, TextEmbedding  # type: ignore
        self.img = ImageEmbedding(model_name=IMG_MODEL)
        self.txt = TextEmbedding(model_name=TXT_MODEL)
        self.name = f"fastembed:{IMG_MODEL}"

    def embed_images(self, paths: list) -> list[list[float]]:
        return [_unit(v) for v in self.img.embed([str(p) for p in paths], batch_size=8)]

    def embed_bytes(self, data: bytes) -> list[float]:
        from PIL import Image  # type: ignore
        im = Image.open(io.BytesIO(data)).convert("RGB")
        return _unit(next(iter(self.img.embed([im]))))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_unit(v) for v in self.txt.embed(texts)]


def build(vis: Vision | None = None) -> dict:
    recs = jload(BUILD / "api" / "kinds.json")["kinds"]
    vis = vis or Vision()
    old = jload(OUT) if OUT.exists() else {"model": None, "items": [], "prototypes": {}}
    if old.get("model") != vis.name:
        old = {"model": vis.name, "items": [], "prototypes": {}}
    have = {it["sha256"]: it for it in old["items"]}
    items, todo = [], []
    for r in recs:
        for im in r.get("images", []):
            p = IMAGES / im["file"]
            if not p.exists():
                continue
            sha = im.get("sha256") or hashlib.sha256(p.read_bytes()).hexdigest()
            meta = {"file": im["file"], "kind": r["id"], "view": im.get("view", ""), "sha256": sha, "license": im.get("license", "")}
            if sha in have:
                items.append({**have[sha], **meta})
            else:
                todo.append((meta, p))
    t0 = time.time()
    if todo:
        vecs = vis.embed_images([p for _, p in todo])
        for (meta, _), v in zip(todo, vecs):
            items.append({**meta, "v": v})
    # text prototypes for every kind — the fallback when no picture exists, and a tie-breaker when one does
    prompts = {r["id"]: f"a photo of a {r['names']['en']}, a Thai amulet: {r['text']['what_en'][:160]}" for r in recs}
    protos = old.get("prototypes") or {}
    need = [k for k, pr in prompts.items() if protos.get(k, {}).get("prompt") != pr]
    if need:
        for k, v in zip(need, vis.embed_texts([prompts[k] for k in need])):
            protos[k] = {"prompt": prompts[k], "v": v}
    protos = {k: v for k, v in protos.items() if k in prompts}
    out = {"model": vis.name, "dim": len(items[0]["v"]) if items else (len(next(iter(protos.values()))["v"]) if protos else 0),
           "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": items, "prototypes": protos}
    jdump(out, OUT, indent=None)
    print(f"image index: {len(items)} pictures ({len(todo)} new) · {len(protos)} text prototypes · {time.time()-t0:.1f}s → {OUT}")
    return out


class Identifier:
    def __init__(self, vis: Vision | None = None):
        if not OUT.exists():
            raise SystemExit("build/image_vectors.json missing — run vision.py --build")
        self.idx = jload(OUT)
        self.vis = vis or Vision()
        if self.vis.name != self.idx["model"]:
            raise SystemExit(f"index built with {self.idx['model']}, this machine embeds with {self.vis.name}")
        self.kinds = {k["id"]: k for k in jload(BUILD / "api" / "index.json")["kinds"]}

    def identify(self, data: bytes, n=5, top_k=3) -> dict:
        q = self.vis.embed_bytes(data)
        # A kind's score blends its single closest picture with the mean of its `top_k`
        # closest. Free coverage is wildly uneven — Commons has 344 keris photographs and
        # two of a phra somdet — and scoring by the maximum alone hands the well-photographed
        # kind that many extra draws on the similarity distribution, so it wins by accident.
        # The mean of the best few asks a better question — do SEVERAL of this kind's
        # pictures look like the photo? — but on its own it demotes a true single match
        # under a kind holding three near-identical images, which the test caught. The blend
        # keeps the best match dominant and damps the lottery-ticket effect. A kind with one
        # picture is unchanged either way, so a thin record is never punished for being thin.
        per: dict[str, list] = {}
        for it in self.idx["items"]:
            s = sum(a * b for a, b in zip(q, it["v"]))
            per.setdefault(it["kind"], []).append((s, it))
        best: dict[str, dict] = {}
        for kind, hits in per.items():
            hits.sort(key=lambda t: -t[0])
            top = hits[:top_k]
            mean_top = sum(s for s, _ in top) / len(top)
            score = 0.65 * top[0][0] + 0.35 * mean_top
            _, it = top[0]
            best[kind] = {"kind": kind, "score": score, "via": "image", "file": it["file"],
                          "license": it.get("license", ""), "pictures": len(hits),
                          "best_single": round(top[0][0], 4), "mean_top": round(mean_top, 4)}
        # Text prototypes: image→text CLIP scores live on a lower scale (~0.2–0.3) than
        # image→image (~0.5–0.9). Used only for kinds with no picture, marked as such.
        for k, pr in self.idx.get("prototypes", {}).items():
            if k in best:
                continue
            s = sum(a * b for a, b in zip(q, pr["v"]))
            best[k] = {"kind": k, "score": s, "via": "text", "file": None, "license": ""}
        rows = sorted(best.values(), key=lambda r: -r["score"])
        top_img = [r for r in rows if r["via"] == "image"][:n]
        top_txt = [r for r in rows if r["via"] == "text"][:3]
        for r in top_img + top_txt:
            # Resemblance labels, measured on this index: an in-bank picture scores 1.0, a
            # random-noise image scored 0.56 against the nearest somdej. So "weak" starts
            # where noise lives. Labels, not verdicts.
            s = r["score"]
            # Bands measured on this index: a picture already in the bank scores 1.00 against
            # itself, and a random-noise image scored 0.56 against its nearest neighbour. So
            # "weak" begins where noise lives, and nothing below it is worth showing as a match.
            r["resemblance"] = ("strong" if s >= 0.82 else "likely" if s >= 0.70 else "weak") if r["via"] == "image" else "by description only"
            k = self.kinds.get(r["kind"], {})
            r["names"] = k.get("names")
            r["class_term"] = k.get("class_term")
            r["what_en"] = k.get("what_en")
            r["what_th"] = k.get("what_th")
            r["score"] = round(r["score"], 4)
        # neighbours: the closest individual pictures, for a "looks like these" strip
        near = sorted(({"file": it["file"], "kind": it["kind"], "score": round(sum(a * b for a, b in zip(q, it["v"])), 4), "license": it.get("license", "")}
                       for it in self.idx["items"]), key=lambda r: -r["score"])[:8]
        return {"model": self.idx["model"], "by_image": top_img, "by_text": top_txt, "nearest_pictures": near,
                "note": "Identifies the KIND by resemblance to free-licensed reference pictures."}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", nargs="?")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("-n", type=int, default=5)
    a = ap.parse_args()
    if a.build:
        build()
        return 0
    if not a.photo:
        ap.error("give a photo, or --build")
    res = Identifier().identify(Path(a.photo).read_bytes(), a.n)
    for r in res["by_image"]:
        print(f"  {r['score']:.3f}  {r['names']['th']:<14} {r['names']['en']:<34} via picture {r['file']}")
    for r in res["by_text"]:
        print(f"  {r['score']:.3f}  {r['names']['th']:<14} {r['names']['en']:<34} via text prototype (no picture yet)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
