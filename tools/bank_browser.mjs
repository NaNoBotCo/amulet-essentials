#!/usr/bin/env node
// bank_browser.mjs — the recogniser bank for the STATIC site, built with the exact model the
// browser runs (Xenova/clip-vit-base-patch32, quantized, transformers.js 2.17.2).
//
// Why a second bank: the Python identifier (tools/vision.py) embeds with fastembed's ONNX
// export of the same CLIP; measured against transformers.js's quantized export, the same
// picture scores only 0.82–0.96 against itself (weights quantized, preprocessing differs).
// A query embedded by one model and compared to a bank built by another returns plausible
// nonsense at the margins, so each bank is built by the model that will query it, and each
// names its model. This one is served as /identify/bank.json and read by identify.js.
//
// Output: build/bank_browser.json — int8 per-vector-scaled vectors (a unit vector's cosine
// survives int8 to ~1e-3), one per reference picture, plus a text prototype per kind for
// kinds with no free picture yet. Resumable: pictures are keyed by sha256.
//
//   node tools/bank_browser.mjs            (needs: npm install, once)
import { AutoProcessor, AutoTokenizer, CLIPVisionModelWithProjection, CLIPTextModelWithProjection, RawImage, env } from '@xenova/transformers';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

env.allowLocalModels = false;
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const KINDS = JSON.parse(fs.readFileSync(path.join(ROOT, 'build/api/kinds.json'), 'utf8')).kinds;
const OUT = path.join(ROOT, 'build/bank_browser.json');
const CACHE = path.join(ROOT, 'build/bank_browser_cache.json');
const MODEL = 'Xenova/clip-vit-base-patch32';
const NAME = `transformers.js@2.17.2:${MODEL}:quantized`;

const unit = v => { let n = 0; for (const x of v) n += x * x; n = Math.sqrt(n) || 1; return v.map(x => x / n); };
const q8 = v => { const m = Math.max(...v.map(Math.abs)) || 1; const s = m / 127; const b = Buffer.alloc(v.length); v.forEach((x, i) => b.writeInt8(Math.round(x / s), i)); return { s: +s.toPrecision(6), q: b.toString('base64') }; };

const cache = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, 'utf8')) : { model: NAME, images: {}, protos: {} };
if (cache.model !== NAME) { cache.images = {}; cache.protos = {}; cache.model = NAME; }
const t0 = Date.now();
const processor = await AutoProcessor.from_pretrained(MODEL);
const vision = await CLIPVisionModelWithProjection.from_pretrained(MODEL, { quantized: true });
console.log(`vision model ready ${((Date.now() - t0) / 1000).toFixed(0)}s`);

const items = []; let fresh = 0;
for (const r of KINDS) {
  for (const im of r.images || []) {
    const p = path.join(ROOT, 'data/images', im.file);
    if (!fs.existsSync(p) || !im.sha256) continue;
    let v = cache.images[im.sha256];
    if (!v) {
      try {
        const img = await RawImage.read(p);
        const out = await vision(await processor(img));
        v = unit(Array.from(out.image_embeds.data)); cache.images[im.sha256] = v; fresh++;
        if (fresh % 50 === 0) { console.log(`  ${fresh} embedded`); fs.writeFileSync(CACHE, JSON.stringify(cache)); }
      } catch (e) { console.error(`  ! ${im.file}: ${e.message}`); continue; }
    }
    items.push({ k: r.id, f: im.file, s: im.sha256, ...q8(v) });
  }
}
fs.writeFileSync(CACHE, JSON.stringify(cache));

const tokenizer = await AutoTokenizer.from_pretrained(MODEL);
const text = await CLIPTextModelWithProjection.from_pretrained(MODEL, { quantized: true });
const protos = {};
for (const r of KINDS) {
  const prompt = `a photo of a ${r.names.en}, a Thai amulet: ${r.text.what_en.slice(0, 160)}`;
  let v = cache.protos[prompt];
  if (!v) { const out = await text(tokenizer([prompt], { padding: true, truncation: true })); v = unit(Array.from(out.text_embeds.data)); cache.protos[prompt] = v; }
  protos[r.id] = q8(v);
}
fs.writeFileSync(CACHE, JSON.stringify(cache));

const kinds = {};
for (const r of KINDS) kinds[r.id] = { th: r.names.th, en: r.names.en, roman: r.names.roman, cls: r.class_facts.term || 'ยังไม่ชี้ขาด', resident: r.class_facts.resident || null, pics: (r.images || []).length, what_th: (r.text.what_th || '').slice(0, 220), what_en: r.text.what_en.slice(0, 220), img: (r.primary_image && r.primary_image.file) || null, sha: (r.primary_image && r.primary_image.sha256) || null };
const out = { model: NAME, dim: 512, built: new Date().toISOString().slice(0, 19), items, protos, kinds };
fs.writeFileSync(OUT, JSON.stringify(out));
console.log(`bank: ${items.length} pictures (${fresh} new) · ${Object.keys(protos).length} prototypes · ${(fs.statSync(OUT).size / 1024).toFixed(0)} KB → ${OUT}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
