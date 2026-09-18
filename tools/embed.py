#!/usr/bin/env python3
"""embed.py — multilingual vectors for every record, from whichever backend is available.

Backends (pick with --backend, default auto):
  local  minishlab/potion-multilingual-128M via model2vec in .venv — distilled from bge-m3,
         runs offline on this laptop, no account, no quota. The resilient default.
  cf     @cf/baai/bge-m3 on Cloudflare Workers AI through the crawler's cfauth — the model
         wichaa.net/search already uses, so vectors made here can later join that index.

The vectors file records the model name. search.py refuses to mix a query embedded with
one model against vectors from another — mixing returns plausible nonsense, not an error.

Resumable: each document carries a content hash; unchanged documents are not re-embedded.

    python3 tools/embed.py                 # auto backend, build/searchdocs.json → build/vectors.json
    python3 tools/embed.py --backend cf
    python3 tools/embed.py --query "ยันต์กันภัย"   # print a query vector's first values (smoke test)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, CRAWLER, jdump, jload  # noqa: E402

LOCAL_MODEL = os.environ.get("AMULET_EMBED_MODEL", "minishlab/potion-multilingual-128M")
CF_ACCOUNT = "fe332688b1b25b543f8429d7f08292a3"
CF_MODEL = "@cf/baai/bge-m3"
DOCS = BUILD / "searchdocs.json"
VECTORS = BUILD / "vectors.json"


class Backend:
    name = ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class Local(Backend):
    def __init__(self):
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from model2vec import StaticModel  # type: ignore
        self.model = StaticModel.from_pretrained(LOCAL_MODEL)
        self.name = f"model2vec:{LOCAL_MODEL}"

    def embed(self, texts):
        v = self.model.encode(texts)
        return [_unit([float(x) for x in row]) for row in v]


class Cloudflare(Backend):
    def __init__(self):
        sys.path.insert(0, str(CRAWLER))
        from crawler import cfauth  # type: ignore
        self.cfauth = cfauth
        self.tok = cfauth.token()
        self.name = f"workers-ai:{CF_MODEL}"
        # Fail fast: a dead OAuth token should be reported now, not after building.
        self.embed(["ทดสอบ"])

    def embed(self, texts):
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/{CF_MODEL}"
        body = json.dumps({"text": texts}).encode()
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, data=body, method="POST", headers={
                    "Authorization": f"Bearer {self.tok}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = json.load(r)
                if not d.get("success"):
                    raise RuntimeError(f"AI error: {d.get('errors')}")
                return [_unit(v) for v in d["result"]["data"]]
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:200]
                if e.code in (401, 403) and attempt == 0:
                    self.tok = self.cfauth.token(force_refresh=True)
                    continue
                raise RuntimeError(f"Workers AI HTTP {e.code}: {detail}") from e
        raise RuntimeError("Workers AI: gave up")


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 6) for x in v]


def backend(kind="auto") -> Backend:
    errs = []
    order = {"auto": ("local", "cf"), "local": ("local",), "cf": ("cf",)}[kind]
    for k in order:
        try:
            return Local() if k == "local" else Cloudflare()
        except Exception as e:  # noqa: BLE001
            errs.append(f"{k}: {type(e).__name__}: {e}")
    raise SystemExit("no embedding backend available:\n  " + "\n  ".join(errs) +
                     "\n  local needs: .venv/bin/pip install model2vec (then run with .venv/bin/python)"
                     "\n  cf needs: a live wrangler login (npx wrangler login — one browser click)")


def doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_vectors() -> dict:
    return jload(VECTORS) if VECTORS.exists() else {"model": None, "dim": 0, "items": {}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="auto", choices=("auto", "local", "cf"))
    ap.add_argument("--query")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    be = backend(a.backend)
    if a.query:
        v = be.embed([a.query])[0]
        print(be.name, len(v), v[:6])
        return 0
    if not DOCS.exists():
        raise SystemExit("build/searchdocs.json missing — run tools/build.py first")
    docs = jload(DOCS)["docs"]
    vec = load_vectors()
    if vec["model"] != be.name or a.force:
        vec = {"model": be.name, "dim": 0, "items": {}}
    todo = [d for d in docs if vec["items"].get(d["id"], {}).get("hash") != doc_hash(d["text"])]
    print(f"{be.name}: {len(docs)} documents, {len(todo)} to embed")
    t0 = time.time()
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        vs = be.embed([d["text"] for d in chunk])
        for d, v in zip(chunk, vs):
            vec["items"][d["id"]] = {"hash": doc_hash(d["text"]), "v": v}
            vec["dim"] = len(v)
    live = {d["id"] for d in docs}
    vec["items"] = {k: v for k, v in vec["items"].items() if k in live}
    vec["built"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    jdump(vec, VECTORS, indent=None)
    print(f"→ {VECTORS}  dim {vec['dim']}  {len(vec['items'])} vectors  {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
