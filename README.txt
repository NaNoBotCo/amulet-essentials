AMULET ESSENTIALS
=================

A structured catalogue of the kinds of sacred object in the Thai and Southeast
Asian amulet world: what each one is, what it is made of, who or what lives in
it, how to tell it from the thing it is most confused with, and a free-to-use
picture with its licence attached. One JSON record per kind. Thai and English
throughout. Built to be read by people and by bots.

WHERE THINGS ARE
----------------
  data/kinds/<id>.json      the records. THE TRUTH. Edit these.
  data/vocab/*.json         snapshot of the wichaa vault vocabularies
                            (class, material, function) + the open region list
  data/sources/sources.json every source a record may cite
  data/images/<id>/         harvested pictures + a .json sidecar each
                            (licence, author, Commons page). _triage/ holds
                            category listings not yet assigned to a kind.
  schema/kind.schema.json   what a record must look like
  tools/                    the pipeline (below)
  build/                    generated. Never edit. Safe to delete.
  build/site/               the static website, ready for any static host
  vendor/                   generated copies of the fleet search core

THE PIPELINE (in order)
-----------------------
  python3 tools/sync_vocab.py        vault -> data/vocab (only when the vault changed)
  python3 tools/validate.py          every record must pass
  python3 tools/build.py             records -> build/api, build/essentials.db,
                                     build/searchdocs.json, search tables
  .venv/bin/python tools/embed.py    meaning vectors (local model, offline)
  python3 tools/site.py              build/site: pages, JSON-LD, sitemap,
                                     llms.txt, robots, CSV/JSONL dumps
  python3 -m unittest discover -s tests

  Or double-click "Amulet Essentials.command" for a numbered menu that runs
  these in order and opens the site.

SEARCH
------
Two halves, fused. Lexical follows the fleet search policy (fuzzy, Thai
compounds split on a dictionary, mined thesaurus, tier reported). Meaning
uses vectors from a multilingual model that runs on this laptop with no
account (model2vec potion-multilingual-128M, distilled from bge-m3; Thai to
English separation measured at +0.169 related vs -0.009 unrelated, the same
as bge-m3's +0.164). The static site runs the lexical half in the browser;
tools/serve.py adds the meaning half at /api/search.

  python3 tools/search.py "ยันต์กันโจร"
  .venv/bin/python tools/search.py "something fed daily that guards a house"

PHOTOGRAPH IT (the sian's reverse-image habit, pointed at our bank)
------------------------------------------------------------------
ON THE LIVE SITE the recogniser runs in the reader's browser (transformers.js,
CLIP ViT-B/32 quantized, ~22 MB downloaded once and cached; then offline).
Many at once from the gallery, or the camera; drag-drop and paste on a desktop;
Share-to-app on Android. A day's haul stays in the browser (IndexedDB) with
corrections and a copyable summary.
  node tools/bank_browser.mjs      build/bank_browser.json — the bank for the
                                   browser, embedded with the SAME model the page
                                   runs (npm install once). site.py copies it to
                                   /identify/bank.json. Re-run after new pictures.
Labels are calibrated on the browser path: a bank picture re-embedded in the
page scores 0.87 against itself, the nearest other kind ~0.67; "strong" needs
0.82 and a 0.04 margin over the runner-up.

LOCALLY (CLI and tools/serve.py):
  .venv/bin/python tools/vision.py --build      CLIP image index over data/images
  .venv/bin/python tools/vision.py photo.jpg    which kinds it resembles
  .venv/bin/python tools/serve.py               adds POST /api/identify; the site's
                                                /identify/ page and the phone Share
                                                sheet (installed PWA, Android) use it
It names the KIND by resemblance to free-licensed reference pictures. It never
says a piece is genuine; every page that shows an answer says so. Scores:
an in-bank picture reads 1.0, random noise read 0.56, so "weak" begins there.

Every picture also gets its own landing page (/kind/<id>/image/<n>/) with
ImageObject JSON-LD and its licence, and the sitemap declares every image with
a bilingual caption. That is what a reverse-image search lands on.

ADDING A KIND
-------------
Copy data/kinds/hun-phayon.json, change every field, keep the id in the
filename, cite only ids in sources.json, run validate.py. Fields you cannot
source stay blank or are tiered "tradition" and hedged. A class the vault
does not place stays null; that refusal is data.

Levels: kind -> variant (a named พิมพ์ or รุ่น, parent = the kind) -> run.
Regions are an open list in data/vocab/regions.json. Keys beginning x_ are
free extension slots the validator never rejects.

IMAGES
------
Only CC0, public domain, CC BY and CC BY-SA are accepted. Non-commercial and
no-derivatives licences are refused by validate.py.
  python3 tools/harvest_commons.py --walk "Category:Phra Kring"
  python3 tools/harvest_commons.py --harvest phra-kring --apply
Your own photographs: drop the file under data/images/<id>/, add an images[]
entry with source "own" and the licence you choose.

ON WICHAA.NET
-------------
Live at wichaa.net/amulets (route in manuscript-wiki/routes.py, featured,
first door, nav "Amulets"). Every publish of wichaa runs
tools/export_wichaa.py (publish_site.sh step 2a-6): pictures are mirrored
into R2 as cas/<sha256> and served at wichaa.net/img/..., the pages are
written into docs/amulets/. Share cards: tools/cards.py renders
publishing/cards/amulets.png and amulets__kind__<id>.png with Chrome;
site_meta copies them to /amulets/card.png and /amulets/kind/<id>/card.png.
Re-run cards.py after new pictures land, then publish.

WHAT IS NOT HERE YET
--------------------
  - non-Thai regions have vocabulary slots but no records
  - SVG diagnostic diagrams for kinds with no free photograph


LICENCE
Records, prose and pages: CC BY-SA 4.0. Other layers — upstream data,
pictures, tools — keep their own terms, set out in LICENSE.

COMMERCIAL LICENCE
If share-alike doesn't fit your use — a corpus, a product, a model — a
commercial licence is available. Open an issue and say what you need:
https://github.com/NaNoBotCo/amulet-essentials/issues

---

Contact: Nan · nan@motdang.net · Sponsor: ko-fi.com/defiantchiangmai · patreon.com/nanobotco
