"""tests — run with:  python3 -m unittest discover -s tests -v   (or .venv/bin/python for the vector half)

Covers: every record validates · build produces the API + DB · search answers golden
queries in Thai AND English within the top 3 · the site carries its bot-legibility files.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

# (query, expected id in top 3) — Thai and English, spelled plainly and misspelled.
GOLDEN = [
    ("พระสมเด็จ", "phra-somdet"),
    ("somdej", "phra-somdet"),
    ("หุ่นพยนต์", "hun-phayon"),
    ("hun payon", "hun-phayon"),
    ("hoon payont", "hun-phayon"),
    ("ตะกรุด", "takrut"),
    ("takrut", "takrut"),
    ("กุมารทอง", "kuman-thong"),
    ("kuman thong", "kuman-thong"),
    ("ปลัดขิก", "palad-khik"),
    ("นางกวัก", "nang-kwak"),
    ("เบี้ยแก้", "bia-kae"),
    ("หลวงปู่ทวด", "luang-pu-thuat"),
    ("พระรอด", "phra-rot"),
]


class Records(unittest.TestCase):
    def test_validate(self):
        r = subprocess.run([sys.executable, str(TOOLS / "validate.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_record_has_thai_and_english(self):
        for p in (ROOT / "data" / "kinds").glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(d["text"].get("what_th"), f"{p.name}: no what_th")
            self.assertTrue(d["text"].get("what_en"), f"{p.name}: no what_en")
            self.assertTrue(d["provenance"]["default"]["tier"], p.name)


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, str(TOOLS / "build.py")], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_api_files(self):
        api = ROOT / "build" / "api"
        self.assertTrue((api / "kinds.json").exists())
        self.assertTrue((api / "index.json").exists())
        idx = json.loads((api / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["count"], len(list((ROOT / "data" / "kinds").glob("*.json"))))
        for k in idx["kinds"]:
            self.assertTrue((api / "kind" / f"{k['id']}.json").exists())

    def test_db(self):
        con = sqlite3.connect(ROOT / "build" / "essentials.db")
        n = con.execute("select count(*) from kinds").fetchone()[0]
        self.assertGreater(n, 0)
        # provenance survives flattening: every field row carries a tier
        self.assertEqual(con.execute("select count(*) from fields where tier is null or tier=''").fetchone()[0], 0)
        # trigram FTS finds Thai substrings
        self.assertGreaterEqual(con.execute("select count(*) from fts where fts match 'สมเด็จ'").fetchone()[0], 1)
        con.close()


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from search import Searcher
        cls.s = Searcher(want_vectors=True)
        cls.ids = {p.stem for p in (ROOT / "data" / "kinds").glob("*.json")}

    def test_golden(self):
        misses = []
        for q, want in GOLDEN:
            if want not in self.ids:
                continue
            got = [r["id"] for r in self.s.search(q, 3)["results"]]
            if want not in got:
                misses.append((q, want, got))
        self.assertFalse(misses, f"golden misses: {misses}")

    def test_tier_reported(self):
        res = self.s.search("somdej", 3)
        self.assertIn(res["worst_tier"], ("exact", "thesaurus", "loose", "partial", "meaning"))

    def test_english_meaning_query(self):
        """A description, not a name. Passes lexically through 'what_en'; better with vectors."""
        if "hun-phayon" not in self.ids:
            self.skipTest("hun-phayon record missing")
        got = [r["id"] for r in self.s.search("effigy that guards the house and is fed", 5)["results"]]
        self.assertIn("hun-phayon", got)


class Vision(unittest.TestCase):
    """Only runs under .venv (fastembed). A picture from the bank must identify as its own kind."""
    @classmethod
    def setUpClass(cls):
        try:
            import fastembed  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("fastembed not installed in this interpreter")
        r = subprocess.run([sys.executable, str(TOOLS / "vision.py"), "--build"], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_bank_picture_identifies_itself(self):
        from vision import Identifier
        idf = Identifier()
        import json as _j
        idx = _j.loads((ROOT / "build" / "image_vectors.json").read_text())
        if not idx["items"]:
            self.skipTest("no pictures harvested yet")
        it = idx["items"][0]
        res = idf.identify((ROOT / "data" / "images" / it["file"]).read_bytes(), 3)
        self.assertEqual(res["by_image"][0]["kind"], it["kind"])
        self.assertEqual(res["by_image"][0]["resemblance"], "strong")


class Analysis(unittest.TestCase):
    """The price analysis: corpus statistics and the charts drawn from them."""
    def test_price_stats_present_and_sane(self):
        p = ROOT / "data" / "analysis" / "price_stats.json"
        if not p.exists():
            self.skipTest("price_stats.json not built")
        d = json.loads(p.read_text(encoding="utf-8"))
        o = d["overall"]
        self.assertGreater(o["n"], 1000)
        self.assertLessEqual(o["p25"], o["median"])
        self.assertLessEqual(o["median"], o["p75"])
        self.assertLessEqual(o["p75"], o["p90"])
        self.assertTrue(d["kinds"] and d["classes"] and d["keywords"])
        for k in d["kinds"]:
            self.assertGreater(k["n"], 0, k["id"])
            self.assertLessEqual(k["p25"], k["median"], k["id"])

    def test_charts_render(self):
        p = ROOT / "data" / "analysis" / "price_stats.json"
        if not p.exists():
            self.skipTest("price_stats.json not built")
        import price_charts
        d = json.loads(p.read_text(encoding="utf-8"))
        for svg in (price_charts.distribution(d["overall"]),
                    price_charts.scatter_kinds(d["kinds"], d["overall"]),
                    price_charts.iqr_bands(d["kinds"]),
                    price_charts.classes_chart(d["classes"], d["overall"]),
                    price_charts.keyword_ladder(d["keywords"], d["overall"])):
            self.assertIn("<svg", svg)
            self.assertIn("</svg>", svg)
            self.assertEqual(svg.count("<svg"), svg.count("</svg>"))
            self.assertIn("<title>", svg)          # per-mark tooltip
            self.assertIn("<details>", svg)        # table twin


class Site(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, str(TOOLS / "site.py")], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.site = ROOT / "build" / "site"

    def test_bot_files(self):
        for f in ("index.html", "robots.txt", "sitemap.xml", "llms.txt", "llms-full.txt", "api/index.json",
                  "api/kinds.json", "search/index.html", "kinds.jsonl", "kinds.csv",
                  "identify/index.html", "manifest.webmanifest", "sw.js", "icon.svg", "feed.xml", "opensearch.xml",
                  "value/index.html", "api/value_factors.json", "api/price_stats.json"):
            self.assertTrue((self.site / f).exists(), f)

    def test_jsonld_on_kind_pages(self):
        pages = list((self.site / "kind").glob("*/index.html"))
        self.assertGreater(len(pages), 0)
        for p in pages:
            html = p.read_text(encoding="utf-8")
            self.assertIn('application/ld+json', html, p)
            self.assertIn('hreflang', html, p)
            self.assertIn('rel="alternate" type="application/json"', html, p)

    def test_image_pages_and_sitemap(self):
        sm = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("sitemap-image", sm)
        for p in (self.site / "kind").glob("*/image/*/index.html"):
            html = p.read_text(encoding="utf-8")
            self.assertIn('"@type": "ImageObject"', html, p)
            self.assertIn("license", html, p)

    def test_identify_page_intake(self):
        html = (self.site / "identify" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="pick" type="file" accept="image/*" multiple', html)      # gallery, many at once, no forced camera
        self.assertIn('id="snap" type="file" accept="image/*" capture="environment"', html)  # camera, opt-in
        self.assertIn("indexedDB", html)                                          # the day's haul persists
        self.assertIn("cdn.jsdelivr.net/npm/@xenova/transformers", html)          # on-device recogniser
        sw = (self.site / "sw.js").read_text()
        self.assertIn("getAll('photo')", sw)                                      # share target takes many
        bank = self.site / "identify" / "bank.json"
        if bank.exists():
            b = json.loads(bank.read_text())
            self.assertTrue(b["items"] and b["kinds"] and b["model"].startswith("transformers.js"))

    def test_lens_arrival_cta(self):
        for p in list((self.site / "kind").glob("*/index.html"))[:5] + list((self.site / "kind").glob("*/image/1/index.html"))[:5]:
            self.assertIn("identify/index.html?kind=", p.read_text(encoding="utf-8"), p)

    def test_no_host_paths(self):
        """wichaa's publish aborts if any built file names the operator's home directory.
        Catching it here means a bad build never reaches that gate."""
        import os
        home = os.path.expanduser("~")
        leaks = []
        for p in self.site.rglob("*"):
            if not p.is_file() or p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"):
                continue
            try:
                if home in p.read_text(encoding="utf-8", errors="ignore"):
                    leaks.append(str(p.relative_to(self.site)))
            except OSError:
                pass
        self.assertFalse(leaks, f"built files name the home directory: {leaks[:5]}")

    def test_robots_open(self):
        txt = (self.site / "robots.txt").read_text()
        self.assertIn("Allow: /", txt)
        self.assertNotIn("Disallow: /\n", txt)


if __name__ == "__main__":
    unittest.main()
