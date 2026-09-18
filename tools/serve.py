#!/usr/bin/env python3
"""serve.py — local server: the built site + a live hybrid search API. Stdlib only.

    python3 tools/serve.py                  # http://127.0.0.1:8793/
    .venv/bin/python tools/serve.py         # same, with meaning search (local model) on

Routes
  /                      build/site/  (static, what a static host would serve)
  /api/search?q=&n=      hybrid Thai/English search → JSON  {results, understood, worst_tier, ...}
  /api/embed?q=          query vector (same model as build/vectors.json) → JSON
  POST /api/identify     photo bytes (or multipart) → kinds it resembles, from vision.py
  /api/*, /images/*      static files from build/ and data/images/

Binds 127.0.0.1 only. The static site works without this server; this server adds the
meaning half of search, which a static host cannot run.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, IMAGES  # noqa: E402

SITE = BUILD / "site"


class Handler(SimpleHTTPRequestHandler):
    searcher = None
    identifier = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(SITE), **kw)

    def log_message(self, fmt, *args):  # quieter
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != "/api/identify":
            self.send_error(404)
            return
        if self.identifier is None:
            return self._json({"error": "photo identification is not available on this machine (build/image_vectors.json missing or fastembed not installed)"}, 503)
        n = int(self.headers.get("Content-Length") or 0)
        if not n or n > 25_000_000:
            return self._json({"error": "send the photo bytes as the request body (max 25 MB)"}, 400)
        data = self.rfile.read(n)
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("multipart/form-data"):
            # a share-target or plain <form> post: take the first file part
            import email
            from email import policy
            msg = email.message_from_bytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + data, policy=policy.default)
            part = next((p for p in msg.iter_parts() if p.get_filename()), None)
            if part is None:
                return self._json({"error": "no file in the form"}, 400)
            data = part.get_payload(decode=True)
        try:
            return self._json(self.identifier.identify(data, n=6))
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"could not read that image: {type(e).__name__}: {e}"}, 400)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/api/search":
            q = (qs.get("q") or [""])[0].strip()
            n = int((qs.get("n") or ["12"])[0])
            if not q:
                return self._json({"query": "", "results": [], "worst_tier": None})
            return self._json(self.searcher.search(q, n))
        if u.path == "/api/embed":
            q = (qs.get("q") or [""])[0].strip()
            if not self.searcher.embedder:
                return self._json({"error": "no embedding backend on this machine", "model": None}, 503)
            return self._json({"model": self.searcher.embedder.name, "v": self.searcher.embedder.embed([q])[0]})
        if u.path.startswith("/images/"):
            p = IMAGES / urllib.parse.unquote(u.path[len("/images/"):])
            if p.is_file() and IMAGES in p.resolve().parents:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream")
                self.send_header("Content-Length", str(p.stat().st_size))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(p.read_bytes())
                return
            self.send_error(404)
            return
        if u.path.startswith("/api/"):
            p = BUILD / urllib.parse.unquote(u.path[1:])
            if p.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(p.stat().st_size))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(p.read_bytes())
                return
        return super().do_GET()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8793)
    ap.add_argument("--no-vectors", action="store_true")
    a = ap.parse_args()
    from search import Searcher
    Handler.searcher = Searcher(want_vectors=not a.no_vectors)
    try:
        from vision import Identifier
        Handler.identifier = Identifier()
    except BaseException as e:  # noqa: BLE001  (SystemExit from a missing index is fine here)
        print(f"photo identification: off ({e})")
    if not SITE.exists():
        print("build/site missing — run tools/site.py first (serving API only)")
        SITE.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"serving http://127.0.0.1:{a.port}/   meaning search: {'on' if Handler.searcher.embedder else 'off'}   photo identification: {'on' if Handler.identifier else 'off'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
