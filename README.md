# Amulet Essentials

A catalogue of the kinds of sacred object in the Thai and wider Southeast Asian
amulet world: what each one is, what it is made of, who or what lives in it, how to
tell it from the thing it gets confused with, and a free picture with its licence
attached.

One JSON record per kind. The emic term leads; English glosses it.

**Live:** https://wichaa.net/amulets

| | |
|---|---|
| kinds | 82, plus 6 the vault declines to place |
| pictures | 774 across 61 kinds, 356 MB, each with a licence sidecar |
| licences | CC BY-SA 291 · public domain 102 · CC0 97 · CC BY 128 · FAL 3 |
| sources | 163 |
| priced listings read | 15,300 |
| reach | Thailand, Cambodia, Laos, Myanmar, Malaysia, Indonesia, Vietnam, the Sino-Southeast-Asian diaspora |

## The record

`data/kinds/<id>.json` is the truth; everything else is generated. A record carries
the term in its own script, a transliteration, the class and material vocabularies
from the wichaa vault, the region list, what lives in the object, the confusions it
attracts, and its sources by id. `tools/validate.py` rejects a record that cites a
source the registry does not hold.

Class `null` means the vault declines to place it — ปลัดขิก, ลูกกรอก, สีผึ้ง, ฤๅษี,
ไอ้ไข่, ชูชก, keris. The site renders those as left to a knower rather than forcing a
slot.

## Pictures

`tools/harvest_commons.py` walks a Commons category into `data/images/_triage/`, then
downloads 1200px renditions with a licence sidecar per file. The allowlist takes CC0,
public domain, CC BY, CC BY-SA and FAL; `validate.py` rejects NC and ND. Filenames
carry the kind, a latin slug and a hash, so a reverse-image search has something to
read.

Each picture gets its own landing page at `/kind/<id>/image/<n>/` with `ImageObject`
JSON-LD and the licence beside it — that page is where Lens and TinEye land.

## Search

Two halves, fused by reciprocal rank.

**Lexical** follows the fleet search core: fuzzy, Thai compounds split on a
dictionary, a mined thesaurus, and the tier reported back to the reader. Vendored
into `vendor/` by `search-core/sync.py` — generated, not edited here.

**Meaning** uses model2vec `potion-multilingual-128M`, distilled from bge-m3 and run
on the laptop. Measured Thai↔English separation: +0.169 related, −0.009 unrelated,
against bge-m3's own +0.164.

The static site runs the lexical half in the browser. `tools/serve.py` adds meaning
search at `/api/search`.

```
python3 tools/search.py "ยันต์กันโจร"
.venv/bin/python tools/search.py "something fed daily that guards a house"
```

## Photograph it

The sian's habit is reverse image search. This points that habit at our own bank.

On the live site the recogniser runs in the reader's browser — transformers.js, CLIP
ViT-B/32 quantized, about 22 MB fetched once and cached, then offline. Gallery
multi-select, camera, drag-drop, paste, and Android Share-to-app. A day's haul sits
in IndexedDB with corrections and a copyable summary.

`node tools/bank_browser.mjs` builds the bank the page queries. It has to be built by
the same model that queries it: fastembed and transformers.js score the same picture
only 0.82–0.96 apart, which is wider than the margin between kinds.

Calibration measured in the page: a bank picture re-thumbnailed scores 0.87 against
itself, the nearest other kind about 0.67. Strong needs ≥0.82 with a margin ≥0.04;
likely needs ≥0.74 with ≥0.015. Score is `0.65·best + 0.35·mean(top3)` per kind —
max alone let a 344-picture kind win by lottery, mean alone demoted true matches.

It names the kind. It does not judge genuineness, and every surface says so.

## /value

`tools/price_charts.py` draws the price analysis as inline SVG, from
`data/analysis/value_factors.json` and `price_stats.json` over 15,300 priced
listings. What the corpus shows:

- Genuineness works as a gate, not a slider.
- The name separates identical forms by 10²–10⁶.
- Gold marks rank rather than carrying value — the same die in gold and copper runs
  25–133×, and the metal in a ฿10M piece is worth about ฿50k.
- Blessedness is priced through the blesser's name, not the rite.
- At retail the resident-bearing classes out-price พระเครื่อง, reversing the sian tier.
- The keyword แท้ lifts a retail price 1.53×.

## For machines

JSON-LD `Dataset` and `DefinedTermSet` on the front, `DefinedTerm` per kind,
`ImageObject` per picture, hreflang th/en, `rel=alternate` JSON. `robots.txt` allows
everything and carries a Content-Signal header. Plus `llms.txt`, `llms-full.txt`, an
Atom feed, OpenSearch, a sitemap with the image extension, and CSV and JSONL dumps.

## Running it

```
python3 tools/sync_vocab.py        # vault → data/vocab, only when the vault moved
python3 tools/validate.py          # every record must pass
python3 tools/build.py             # → build/api, essentials.db, search tables
.venv/bin/python tools/embed.py    # meaning vectors, local model
python3 tools/site.py              # → build/site
python3 -m unittest discover -s tests
```

Or double-click `Amulet Essentials.command` for a numbered menu.

Stdlib Python for the pipeline; the vector and vision tools want the `.venv`.
`README.txt` is the fuller guide.

## Licence

Records CC BY-SA 4.0. Pictures carry their own licences, stated per file and beside each
one on the site. Code MIT.

**Commercial licence.** If share-alike doesn't fit your use — a corpus, a
product, a model — a commercial licence is available.
[Open an issue](https://github.com/NaNoBotCo/amulet-essentials/issues) and say what you need.
