#!/usr/bin/env python3
"""search.py — Thai + English search over the records: lexical (fleet search-core) + meaning (vectors), fused.

Lexical follows the fleet policy (intent → segment → thesaurus → loose) and reports its tier.
Meaning uses build/vectors.json with the SAME model that built it — a query embedded by
another model is refused, never silently mixed. The two lists are fused by reciprocal rank,
which needs no shared score scale, so either half can be absent (no vectors yet, no
embedding backend on this machine) and the search still answers with what it has.

    python3 tools/search.py "ยันต์กันโจร"
    python3 tools/search.py "something that guards the house and is fed" --json
    .venv/bin/python tools/search.py "หุ่นพยน" -n 5      # (the venv has the local embedding model)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, DATA, SEARCH_CORE, jload, search_core  # noqa: E402

TIER_TH = {"exact": "ตรงคำ", "thesaurus": "คำพ้อง", "loose": "ใกล้เคียง", "partial": "บางส่วน", "meaning": "ตามความหมาย"}
TIER_EN = {"exact": "exact", "thesaurus": "same meaning, other word", "loose": "near spelling — closest first",
           "partial": "partial", "meaning": "by meaning"}


class Searcher:
    def __init__(self, want_vectors=True):
        self.sc, core_dir = search_core()
        groups, words = [], []
        for p in (SEARCH_CORE / "data" / "thesaurus.json", SEARCH_CORE / "data" / "wichaa.thesaurus.json",
                  DATA / "search" / "amulets.thesaurus.json"):
            if p.exists():
                d = jload(p)
                groups.extend(d["groups"] if isinstance(d, dict) else d)
        for p in (SEARCH_CORE / "data" / "segdict.txt", SEARCH_CORE / "data" / "wichaa.segdict.txt",
                  DATA / "search" / "amulets.segdict.txt"):
            if p.exists():
                words.extend(w for w in p.read_text(encoding="utf-8").split("\n") if w.strip() and not w.startswith("#"))
        self.core = self.sc.SearchCore(self.sc.Thesaurus(groups), self.sc.Segmenter(words))
        idx = jload(BUILD / "api" / "index.json")["kinds"]
        full = {k["id"]: k for k in jload(BUILD / "api" / "kinds.json")["kinds"]}
        self.by_id = full
        self.prepared: dict[str, dict] = {}
        self.index = self.sc.Index(self.core)
        for k in idx:
            r = full[k["id"]]
            n = r["names"]
            al = n.get("aliases") or {}
            name = " ".join([n["th"], n["roman"], n["en"]] + list((n.get("other_scripts") or {}).values()) + al.get("th", []) + al.get("roman", []) + al.get("en", []))
            terms = " ".join([r["class_facts"].get("term") or "", r["class_facts"].get("en_gloss") or ""]
                             + [f"{t['term']} {t['en']}" for t in r["function_terms"] + r["material_terms"]]
                             + [f"{t.get('th','')} {t.get('en','')}" for t in r["region_terms"]])
            text = " ".join([r["text"].get("what_th", ""), r["text"]["what_en"], r["text"].get("story_en", ""),
                             r["text"].get("keeping_en", "")] + [f"{i.get('th','')} {i.get('en','')}" for i in r.get("iconography", [])]
                            + [f"{d.get('th','')} {d.get('en','')}" for d in r.get("diagnostics", [])])
            fields = {"name": (name, 3.0), "terms": (terms, 2.0), "text": (text, 1.0)}
            # The Index is kept as the mending oracle (it knows this corpus's words);
            # scoring goes document by document through score_doc, as the fleet policy
            # says for corpora under ~1,000 — and because a two-word name like
            # "kuman thong" is a whole thesaurus phrase that word postings can never
            # match exactly, while score_doc's substring test can.
            self.index.add(k["id"], fields)
            self.prepared[k["id"]] = self.core.prepare_doc(fields)
        self.index.finalize()
        self.vectors = None
        self.embedder = None
        if want_vectors and (BUILD / "vectors.json").exists():
            v = jload(BUILD / "vectors.json")
            self.vectors = v
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import embed  # noqa: E402
                if v["model"].startswith("model2vec:"):
                    self.embedder = embed.Local()
                elif v["model"].startswith("workers-ai:"):
                    self.embedder = embed.Cloudflare()
                if self.embedder and self.embedder.name != v["model"]:
                    self.embedder = None
                    self.vector_note = f"vectors were built with {v['model']}; this machine cannot embed with it"
            except Exception as e:  # noqa: BLE001
                self.embedder = None
                self.vector_note = f"meaning search unavailable here: {type(e).__name__}: {e}"

    # -- halves -----------------------------------------------------------
    def lexical(self, q: str, limit=50):
        an = self.core.analyze(q, oracle=self.index)
        rows = []
        for did, prep in self.prepared.items():
            r = self.core.score_doc(an, prep)
            if r:
                # a kind outranks its own variants on an equal match (พระสมเด็จ before จิตรลดา)
                lvl = 1.0 if self.by_id[did].get("level", "kind") == "kind" else 0.95
                rows.append((did, r["score"] * lvl, r["tier"], r["coverage"]))
        # Loosen by steps: documents matching every term are the answer; documents
        # matching some are a fallback, offered only when there is no answer.
        whole = [r for r in rows if r[3] >= 1.0]
        kept = whole or rows
        kept.sort(key=lambda r: -r[1])
        return [(did, score, tier) for did, score, tier, _ in kept[:limit]], an

    def meaning(self, q: str, limit=20):
        if not (self.vectors and self.embedder):
            return []
        qv = self.embedder.embed([q])[0]
        items = self.vectors["items"]
        scored = [(i, sum(a * b for a, b in zip(qv, d["v"]))) for i, d in items.items()]
        scored.sort(key=lambda t: -t[1])
        top = scored[:limit]
        if not top:
            return []
        # A vector search always returns something. Keep only neighbours that stand out
        # from the field: within a margin of the best and above the corpus mean by a
        # clear step. A plain "nothing close" beats four polite non-answers.
        if len(scored) < 5:
            return top
        mean = sum(s for _, s in scored) / len(scored)
        sd = math.sqrt(sum((s - mean) ** 2 for _, s in scored) / max(1, len(scored) - 1)) or 1e-6
        return [(i, s) for i, s in top if (s - mean) / sd >= 1.0]

    # -- fusion -----------------------------------------------------------
    def search(self, q: str, n=10) -> dict:
        lex, an = self.lexical(q)
        sem = self.meaning(q)
        K = 60.0
        fused: dict[str, dict] = {}
        for rank, (doc, score, tier) in enumerate(lex, 1):
            f = fused.setdefault(doc, {"id": doc, "score": 0.0, "tier": tier, "lexical": score, "meaning": None})
            f["score"] += 1.0 / (K + rank)
        for rank, (doc, s) in enumerate(sem, 1):
            f = fused.setdefault(doc, {"id": doc, "score": 0.0, "tier": "meaning", "lexical": None, "meaning": None})
            f["score"] += 1.0 / (K + rank)
            f["meaning"] = round(s, 4)
        # Loosen by steps, never all at once (fleet policy): an exact hit is the answer,
        # a thesaurus hit the next answer, a meaning-only neighbour a good fallback, a
        # near-spelling or partial hit the last resort. Fused score orders WITHIN a step.
        step = {"exact": 0, "thesaurus": 1, "meaning": 2, "loose": 3, "partial": 4}
        out = sorted(fused.values(), key=lambda f: (step.get(f["tier"], 5), -(f["lexical"] or 0.0), -f["score"]))[:n]
        for f in out:
            r = self.by_id[f["id"]]
            f["names"] = r["names"]
            f["what_en"] = r["text"]["what_en"]
            f["what_th"] = r["text"].get("what_th", "")
            f["class"] = r["class_facts"].get("term")
            f["image"] = (r.get("primary_image") or {}).get("file")
            f["tier_label"] = {"en": TIER_EN.get(f["tier"], f["tier"]), "th": TIER_TH.get(f["tier"], f["tier"])}
        worst = max((self.sc.TIER_ORDER.index(f["tier"]) for f in out if f["tier"] in self.sc.TIER_ORDER), default=None)
        return {
            "query": q,
            "understood": an.as_dict(),
            "results": out,
            "worst_tier": self.sc.TIER_ORDER[worst] if worst is not None else ("meaning" if out else None),
            "meaning_available": bool(self.embedder),
            "meaning_note": getattr(self, "vector_note", ""),
            "vector_model": (self.vectors or {}).get("model"),
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-vectors", action="store_true")
    a = ap.parse_args()
    s = Searcher(want_vectors=not a.no_vectors)
    res = s.search(a.query, a.n)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print(f"{a.query!r}  → {len(res['results'])} result(s)  worst tier: {res['worst_tier']}  meaning: {'on' if res['meaning_available'] else 'off'}")
    if res["meaning_note"]:
        print("  ", res["meaning_note"])
    for f in res["results"]:
        print(f"  {f['names']['th']:<16} {f['names']['en']:<34} [{f['tier']}]  lex={f['lexical']} mean={f['meaning']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
