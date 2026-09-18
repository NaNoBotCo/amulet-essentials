/* identify.js — "I photographed it", running entirely on the reader's device.
 *
 * The recogniser (CLIP ViT-B/32, quantized, transformers.js) downloads once (~22 MB, cached
 * by the browser afterwards) and every photo is embedded here, on the phone. Nothing is
 * uploaded anywhere: a sian's pieces stay private, and the page keeps working offline once
 * the model and the bank are cached. Photos and results persist in IndexedDB so a day's
 * shopping can be reviewed, corrected and shared that evening.
 *
 * Injected into /identify/ by site.py; the page supplies window.IDENT = {imgBase, siteUrl,
 * kind (optional ?kind= framing)}. Bank: ./bank.json built by tools/bank_browser.mjs with
 * the SAME model, so query and bank never disagree.
 */
(function () {
  "use strict";
  var CFG = window.IDENT || {};
  var TJS = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2";
  var MODEL = "Xenova/clip-vit-base-patch32";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var T = {
    th: { ready: "พร้อมแล้ว · เลือกรูปหรือถ่ายได้เลย", loading: "กำลังโหลดตัวจำแนก", bank: "กำลังโหลดคลังภาพอ้างอิง", identifying: "กำลังส่อง…", queued: "รอคิว", done: "เสร็จแล้ว",
          nomodel: "โหลดตัวจำแนกไม่ได้ในเครื่องนี้ — ใช้ค้นหาด้วยคำแทน", offline: "ออฟไลน์ · ใช้ได้เพราะเคยโหลดไว้แล้ว", strong: "คล้ายมาก", likely: "น่าจะใช่", weak: "คล้ายเล็กน้อย", text: "ยังไม่มีภาพอ้างอิง · เทียบจากคำอธิบาย",
          haul: "ของวันนี้", photos: "รูป", kinds: "ชนิด", copied: "คัดลอกแล้ว", cleared: "ล้างแล้ว" },
    en: { ready: "Ready — choose photos or take one", loading: "Downloading the recogniser", bank: "Loading the reference bank", identifying: "Looking…", queued: "queued", done: "done",
          nomodel: "The recogniser cannot load on this device — use the text search instead", offline: "offline · works because it was loaded before", strong: "strong resemblance", likely: "likely", weak: "weak resemblance", text: "no reference picture yet — matched by description",
          haul: "Today's haul", photos: "photos", kinds: "kinds", copied: "copied", cleared: "cleared" }
  };
  var t = function (k) { return T.th[k] + " · " + T.en[k]; };

  // ---------------------------------------------------------------- storage (IndexedDB)
  var DB = null;
  function db() {
    if (DB) return Promise.resolve(DB);
    return new Promise(function (res, rej) {
      var r = indexedDB.open("amulet-identify", 1);
      r.onupgradeneeded = function () { r.result.createObjectStore("photos", { keyPath: "id" }); };
      r.onsuccess = function () { DB = r.result; res(DB); };
      r.onerror = function () { rej(r.error); };
    });
  }
  function put(rec) { return db().then(function (d) { return new Promise(function (res, rej) { var tx = d.transaction("photos", "readwrite"); tx.objectStore("photos").put(rec); tx.oncomplete = res; tx.onerror = function () { rej(tx.error); }; }); }).catch(function () {}); }
  function all() { return db().then(function (d) { return new Promise(function (res) { var out = []; var c = d.transaction("photos").objectStore("photos").openCursor(); c.onsuccess = function () { var cur = c.result; if (cur) { out.push(cur.value); cur.continue(); } else res(out); }; c.onerror = function () { res([]); }; }); }).catch(function () { return []; }); }
  function del(id) { return db().then(function (d) { d.transaction("photos", "readwrite").objectStore("photos").delete(id); }).catch(function () {}); }
  function clearAll() { return db().then(function (d) { d.transaction("photos", "readwrite").objectStore("photos").clear(); }).catch(function () {}); }

  // ---------------------------------------------------------------- bank
  var BANK = null; // {model, items:[{k,f,s,v:Float32Array}], protos:{k:Float32Array}, kinds:{}}
  function deq(s, b64) { var bin = atob(b64); var v = new Float32Array(bin.length); for (var i = 0; i < bin.length; i++) { var x = bin.charCodeAt(i); v[i] = (x > 127 ? x - 256 : x) * s; } return v; }
  function loadBank() {
    status(t("bank"));
    return fetch("bank.json").then(function (r) { if (!r.ok) throw new Error("bank " + r.status); return r.json(); }).then(function (b) {
      b.items.forEach(function (it) { it.v = deq(it.s, it.q); delete it.q; });
      var p = {}; Object.keys(b.protos).forEach(function (k) { p[k] = deq(b.protos[k].s, b.protos[k].q); }); b.protos = p;
      BANK = b; return b;
    });
  }

  // ---------------------------------------------------------------- model
  var TJ = null, PROC = null, VISION = null, modelFailed = false;
  function loadModel() {
    if (VISION) return Promise.resolve(VISION);
    status(t("loading") + " (≈22 MB, once)");
    return import(TJS).then(function (m) {
      TJ = m; m.env.allowLocalModels = false; m.env.useBrowserCache = true;
      var seen = {};
      var prog = function (p) {
        if (p.status === "progress" && p.file) { seen[p.file] = p.progress || 0; var files = Object.keys(seen); var avg = files.reduce(function (a, f) { return a + seen[f]; }, 0) / files.length; bar(avg); }
        if (p.status === "ready") bar(100);
      };
      return Promise.all([
        m.AutoProcessor.from_pretrained(MODEL, { progress_callback: prog }),
        m.CLIPVisionModelWithProjection.from_pretrained(MODEL, { quantized: true, progress_callback: prog })
      ]);
    }).then(function (r) { PROC = r[0]; VISION = r[1]; bar(-1); return VISION; }).catch(function (e) { modelFailed = true; bar(-1); status(t("nomodel") + " — " + esc(e.message)); throw e; });
  }
  function embed(blob) {
    return TJ.RawImage.fromBlob(blob).then(function (img) { return PROC(img); }).then(function (inp) { return VISION(inp); }).then(function (out) {
      var v = out.image_embeds.data, n = 0; for (var i = 0; i < v.length; i++) n += v[i] * v[i]; n = Math.sqrt(n) || 1;
      var u = new Float32Array(v.length); for (var j = 0; j < v.length; j++) u[j] = v[j] / n; return u;
    });
  }

  // ---------------------------------------------------------------- scoring (mirrors tools/vision.py)
  function dot(a, b) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }
  function score(q) {
    var per = {};
    BANK.items.forEach(function (it) { var s = dot(q, it.v); (per[it.k] = per[it.k] || []).push({ s: s, f: it.f, sha: it.s }); });
    var rows = [];
    Object.keys(per).forEach(function (k) {
      var h = per[k].sort(function (a, b) { return b.s - a.s; }); var top = h.slice(0, 3);
      var mean = top.reduce(function (a, x) { return a + x.s; }, 0) / top.length;
      rows.push({ kind: k, score: 0.65 * top[0].s + 0.35 * mean, best: top[0].s, via: "image", file: top[0].f, sha: top[0].sha, pictures: h.length });
    });
    Object.keys(BANK.protos).forEach(function (k) { if (!per[k]) rows.push({ kind: k, score: dot(q, BANK.protos[k]), via: "text", pictures: 0 }); });
    rows.sort(function (a, b) { return b.score - a.score; });
    // Calibrated on the BROWSER path, measured in the page (2026-09-02): a bank picture,
    // re-thumbnailed by this page and embedded here, scores 0.87 against its own bank
    // vector (the bank was embedded in Node from the original file; resampling differs),
    // and the nearest picture of a DIFFERENT kind then sits near 0.67. So an absolute score
    // alone says little; what separates a real match is the MARGIN over the runner-up.
    // Labels, never verdicts — and the runner-up's score is shown so the margin is visible.
    var imgs = rows.filter(function (r) { return r.via === "image"; });
    imgs.forEach(function (r, i) {
      var next = imgs[i + 1] ? imgs[i + 1].score : 0; r.margin = r.score - next;
      r.band = (r.score >= 0.82 && r.margin >= 0.04) ? "strong" : (r.score >= 0.74 && r.margin >= 0.015) ? "likely" : "weak";
    });
    rows.forEach(function (r) { if (r.via === "text") r.band = "text"; });
    var near = [];
    BANK.items.forEach(function (it) { near.push({ s: dot(q, it.v), f: it.f, sha: it.s, k: it.k }); });
    near.sort(function (a, b) { return b.s - a.s; });
    return { byImage: rows.filter(function (r) { return r.via === "image"; }).slice(0, 5), byText: rows.filter(function (r) { return r.via === "text"; }).slice(0, 2), near: near.slice(0, 6), all: rows };
  }

  // ---------------------------------------------------------------- photos in, thumbnails
  function thumb(file, max) {
    return new Promise(function (res, rej) {
      var url = URL.createObjectURL(file); var img = new Image();
      img.onload = function () {
        var s = Math.min(1, max / Math.max(img.width, img.height)); var c = document.createElement("canvas");
        c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
        c.toBlob(function (b) { b ? res(b) : rej(new Error("thumbnail")); }, "image/jpeg", 0.86);
      };
      img.onerror = function () { URL.revokeObjectURL(url); rej(new Error("not an image")); };
      img.src = url;
    });
  }
  var QUEUE = [], BUSY = false;
  function intake(files) {
    var list = Array.prototype.slice.call(files || []).filter(function (f) { return f && (f.type || "").indexOf("image/") === 0 || /\.(jpe?g|png|webp|heic|heif)$/i.test(f.name || ""); });
    if (!list.length) { status("ไม่พบรูป · no image in that selection"); return; }
    list.forEach(function (f) {
      var rec = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7), name: f.name || "photo", added: Date.now(), state: "queued", result: null, correction: null };
      thumb(f, 640).then(function (b) { rec.thumb = b; return put(rec); }).then(function () { render(rec, true); QUEUE.push(rec); pump(); })
        .catch(function (e) { status(esc(f.name || "photo") + ": " + esc(e.message)); });
    });
  }
  function pump() {
    if (BUSY || !QUEUE.length) return;
    BUSY = true; var rec = QUEUE.shift(); rec.state = "working"; render(rec);
    Promise.all([loadBank(), loadModel()]).then(function () { return embed(rec.thumb); }).then(function (q) {
      rec.result = score(q); rec.state = "done"; return put(rec);
    }).catch(function (e) { rec.state = "error"; rec.error = e.message; }).then(function () { render(rec); BUSY = false; haul(); status(QUEUE.length ? T.th.identifying + " · " + QUEUE.length + " " + t("queued") : t("ready")); pump(); });
  }

  // ---------------------------------------------------------------- render
  var kindUrl = function (k) { return "../kind/" + encodeURIComponent(k) + "/index.html"; };
  var picUrl = function (r) { return CFG.imgBase && r.sha ? CFG.imgBase + "/" + r.sha + (r.file || r.f || "").slice((r.file || r.f || "").lastIndexOf(".")).toLowerCase() : "../images/" + (r.file || r.f); };
  function kindMeta(k) { return (BANK && BANK.kinds[k]) || { th: k, en: "", cls: "" }; }
  function bandLabel(b) { return T.th[b] + " · " + T.en[b]; }
  function render(rec, fresh) {
    var el = $("p-" + rec.id);
    if (!el) { el = document.createElement("article"); el.id = "p-" + rec.id; el.className = "shot"; $("shots").prepend(el); }
    if (rec.thumb && !el.querySelector("img")) { var im = document.createElement("img"); im.alt = "your photo"; im.src = URL.createObjectURL(rec.thumb); el.appendChild(im); }
    var body = el.querySelector(".shotbody") || el.appendChild(Object.assign(document.createElement("div"), { className: "shotbody" }));
    var html = "";
    if (rec.state === "queued") html = '<p class="mute">' + t("queued") + "</p>";
    else if (rec.state === "working") html = '<p class="mute">' + t("identifying") + "</p>";
    else if (rec.state === "error") html = '<p class="mute">⚠ ' + esc(rec.error) + "</p>";
    else if (rec.result) {
      var R = rec.result, top = rec.correction ? { kind: rec.correction, band: "corrected" } : R.byImage[0] || R.byText[0];
      var m = kindMeta(top.kind);
      html += '<a class="t" href="' + kindUrl(top.kind) + '"><span class="th">' + esc(m.th) + "</span> · " + esc(m.en) + "</a>";
      html += '<p class="mute">' + esc(m.cls) + "</p>";
      var runner = R.byImage[1];
      html += '<p><span class="chip band-' + esc(top.band) + '">' + (rec.correction ? "คุณระบุเอง · you picked this" : bandLabel(top.band) + (top.score != null ? " · " + top.score.toFixed(2) : "")) + "</span>"
           + (!rec.correction && runner ? ' <span class="mute">next: ' + esc(kindMeta(runner.kind).th) + " " + runner.score.toFixed(2) + "</span>" : "") + "</p>";
      if (CFG.kind && BANK) { var rank = R.all.findIndex(function (r) { return r.kind === CFG.kind; }); var cm = kindMeta(CFG.kind); if (rank >= 0) html += '<p class="mute">' + esc(cm.th) + " ranked #" + (rank + 1) + (R.all[rank].score != null ? " · " + R.all[rank].score.toFixed(2) : "") + "</p>"; }
      html += '<details><summary>ตัวเลือกอื่น · other candidates</summary><ol>';
      R.byImage.slice(1).concat(R.byText).forEach(function (r) { var mm = kindMeta(r.kind); html += '<li><a href="' + kindUrl(r.kind) + '"><span class="th">' + esc(mm.th) + "</span> · " + esc(mm.en) + '</a> <span class="mute">' + bandLabel(r.band) + (r.score != null ? " " + r.score.toFixed(2) : "") + "</span></li>"; });
      html += "</ol>";
      if (R.near && R.near.length) { html += '<div class="near">'; R.near.forEach(function (n) { html += '<a href="' + kindUrl(n.k) + '" title="' + esc(kindMeta(n.k).th) + " " + n.s.toFixed(2) + '"><img loading="lazy" alt="" src="' + esc(picUrl(n)) + '"></a>'; }); html += "</div>"; }
      html += "</details>";
      html += '<label class="fix">ไม่ใช่? เลือกชนิดที่ถูก · not this? pick the right kind <select data-id="' + rec.id + '"><option value="">—</option>' + Object.keys(BANK ? BANK.kinds : {}).sort(function (a, b) { return kindMeta(a).th.localeCompare(kindMeta(b).th, "th"); }).map(function (k) { return '<option value="' + esc(k) + '"' + (rec.correction === k ? " selected" : "") + ">" + esc(kindMeta(k).th) + " · " + esc(kindMeta(k).en) + "</option>"; }).join("") + "</select></label>";
    }
    html += '<button type="button" class="ghost del" data-id="' + rec.id + '" aria-label="remove">✕ ลบ · remove</button>';
    body.innerHTML = html;
    if (fresh) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function haul() {
    all().then(function (recs) {
      var done = recs.filter(function (r) { return r.state === "done" || r.correction; });
      var kinds = {}; done.forEach(function (r) { var k = r.correction || (r.result && r.result.byImage[0] && r.result.byImage[0].kind) || (r.result && r.result.byText[0] && r.result.byText[0].kind); if (k) kinds[k] = (kinds[k] || 0) + 1; });
      var ks = Object.keys(kinds);
      $("haul").hidden = !recs.length;
      $("haulhead").textContent = t("haul") + ": " + recs.length + " " + t("photos") + " · " + ks.length + " " + t("kinds");
      $("haullist").innerHTML = ks.sort(function (a, b) { return kinds[b] - kinds[a]; }).map(function (k) { var m = kindMeta(k); return '<li><a href="' + kindUrl(k) + '"><span class="th">' + esc(m.th) + "</span> · " + esc(m.en) + "</a> <span class=\"count\">(" + kinds[k] + ")</span></li>"; }).join("");
      window.__haulText = ks.map(function (k) { var m = kindMeta(k); return m.th + " · " + m.en + " ×" + kinds[k] + "  " + (CFG.siteUrl || "") + "/kind/" + k + "/"; }).join("\n");
    });
  }
  function status(s) { $("status").innerHTML = s; }
  function bar(pct) { var b = $("bar"); if (pct < 0) { b.hidden = true; return; } b.hidden = false; b.value = pct; b.textContent = Math.round(pct) + "%"; }

  // ---------------------------------------------------------------- wire up
  function init() {
    $("pick").addEventListener("change", function () { intake(this.files); this.value = ""; });
    $("snap").addEventListener("change", function () { intake(this.files); this.value = ""; });
    var drop = $("drop");
    ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
    drop.addEventListener("drop", function (e) { intake(e.dataTransfer.files); });
    document.addEventListener("paste", function (e) { var fs = []; Array.prototype.forEach.call((e.clipboardData || {}).items || [], function (it) { if (it.kind === "file") fs.push(it.getAsFile()); }); if (fs.length) intake(fs); });
    $("shots").addEventListener("click", function (e) { var b = e.target.closest(".del"); if (b) { del(b.dataset.id); var el = $("p-" + b.dataset.id); if (el) el.remove(); haul(); } });
    $("shots").addEventListener("change", function (e) { var s = e.target.closest("select[data-id]"); if (!s) return; all().then(function (recs) { var rec = recs.find(function (r) { return r.id === s.dataset.id; }); if (!rec) return; rec.correction = s.value || null; put(rec).then(function () { render(rec); haul(); }); }); });
    $("copy").addEventListener("click", function () { var txt = ($("haulhead").textContent + "\n" + (window.__haulText || "")); (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(function () { status(t("copied")); }, function () { window.prompt("copy:", txt); }); });
    $("share").addEventListener("click", function () { var txt = ($("haulhead").textContent + "\n" + (window.__haulText || "")); if (navigator.share) navigator.share({ title: "Amulet Essentials", text: txt }).catch(function () {}); else $("copy").click(); });
    $("clear").addEventListener("click", function () { if (!confirm("ล้างรูปทั้งหมดในเครื่องนี้? · Remove every photo kept on this device?")) return; clearAll().then(function () { $("shots").innerHTML = ""; haul(); status(t("cleared")); }); });
    if (!navigator.share) $("share").hidden = true;
    // a photo shared into the installed app arrives via the service worker, parked in the cache
    var u = new URL(location.href);
    if (u.searchParams.get("shared") === "1" && window.caches) {
      caches.open("shared-photo").then(function (c) { return c.keys().then(function (keys) { return Promise.all(keys.map(function (k) { return c.match(k).then(function (r) { return r && r.blob(); }).then(function (b) { c.delete(k); return b; }); })); }); })
        .then(function (blobs) { var fs = blobs.filter(Boolean).map(function (b, i) { return new File([b], "shared-" + (i + 1) + ".jpg", { type: b.type || "image/jpeg" }); }); if (fs.length) { status("รับรูปจาก Share แล้ว · received " + fs.length + " from Share"); intake(fs); } }).catch(function () {});
    }
    if (CFG.kind) { $("frame").hidden = false; }
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("../sw.js").catch(function () {});
    all().then(function (recs) { recs.sort(function (a, b) { return a.added - b.added; }).forEach(function (r) { if (r.state === "working" || r.state === "queued") { r.state = "queued"; QUEUE.push(r); } render(r); }); haul(); if (QUEUE.length) pump(); });
    loadBank().then(function (b) { if (CFG.kind && b.kinds[CFG.kind]) { var m = b.kinds[CFG.kind]; $("framekind").innerHTML = '<span class="th">' + esc(m.th) + "</span> · " + esc(m.en); } status(t("ready") + (navigator.onLine ? "" : " · " + t("offline"))); }).catch(function (e) { status("bank: " + esc(e.message)); });
    // warm the model in the background on a good connection so the first photo is not the slow one
    var c = navigator.connection; if (!c || !c.saveData) loadModel().catch(function () {});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
