#!/usr/bin/env python3
"""export_wichaa.py — put the catalogue on wichaa.net: pictures to R2, pages into the site build.

Run by manuscript-wiki/publishing/publish_site.sh (step 2a-6) on every publish, and by hand:

    python3 tools/export_wichaa.py --docs ../nanobotco-lanna/docs --site-url https://wichaa.net
    python3 tools/export_wichaa.py --docs ... --skip-r2      # pages only (offline)

What it does
  1. Stages every record picture as <sha256><ext> and mirrors it into R2 bucket
     `wichaa-images` under `cas/` — the content-addressed store the wichaa-router Worker
     already serves at wichaa.net/img/<key> with immutable caching. Same uploader the
     manuscript plates use (cloudflare-mirror/r2_put_tree.py, incremental by MD5/ETag), so
     an unchanged picture costs a listing and nothing else. Nothing image-sized enters the
     Pages deployment (the 20,000-file cap is why pimg moved to R2 in the first place).
  2. Builds the static site with SITE_URL=<site-url>/amulets and IMAGE_BASE=<site-url>/img
     into <docs>/amulets/ — the route routes.py declares, so verify_build guards it.
  3. Share cards: publishing/cards/amulets.png and amulets__kind__<id>.png are committed
     masters (tools/cards.py renders them with Chrome); site_meta.py copies them to
     /amulets/card.png and /amulets/kind/<id>/card.png by its "__" convention.

Auth for R2: CLOUDFLARE_API_TOKEN in the environment (deploy.sh exports the fleet token
from ~/.config/nanobotco/keys.json; this script does the same when the variable is unset).
A failed upload aborts the export — publishing pages whose pictures are not in the bucket
would ship 517 broken images, which is worse than a delayed publish.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, IMAGES, PROJECTS, jload  # noqa: E402

R2_PUT_TREE = PROJECTS / "cloudflare-mirror" / "r2_put_tree.py"
CARDS = PROJECTS / "manuscript-wiki" / "publishing" / "cards"
KEYS = Path.home() / ".config" / "nanobotco" / "keys.json"
BUCKET, PREFIX = "wichaa-images", "cas/"


def fleet_token() -> str:
    t = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if t:
        return t
    try:
        return json.load(open(KEYS))["cloudflare"]["api_token"].strip()
    except Exception:  # noqa: BLE001
        return ""


def stage_pictures(tmp: Path) -> int:
    recs = jload(BUILD / "api" / "kinds.json")["kinds"]
    n = 0
    for r in recs:
        for im in r.get("images", []):
            src = IMAGES / im["file"]
            if not src.exists() or not im.get("sha256"):
                continue
            dst = tmp / f"{im['sha256']}{src.suffix.lower()}"
            if not dst.exists():
                os.link(src, dst) if src.stat().st_dev == tmp.stat().st_dev else shutil.copy2(src, dst)
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True)
    ap.add_argument("--site-url", default="https://wichaa.net")
    ap.add_argument("--skip-r2", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    docs = Path(a.docs).resolve()
    site_url = a.site_url.rstrip("/")
    py = sys.executable
    here = Path(__file__).resolve().parent

    if not (BUILD / "api" / "kinds.json").exists():
        r = subprocess.run([py, str(here / "build.py")])
        if r.returncode:
            return r.returncode

    if not a.skip_r2:
        tok = fleet_token()
        if not tok:
            print("export_wichaa: no Cloudflare token (CLOUDFLARE_API_TOKEN or keys.json) — pictures not uploaded; aborting")
            return 2
        if not R2_PUT_TREE.exists():
            print(f"export_wichaa: {R2_PUT_TREE} missing; aborting")
            return 2
        with tempfile.TemporaryDirectory(prefix="amulet-cas-", dir=str(IMAGES.parent)) as tmp:
            n = stage_pictures(Path(tmp))
            print(f"export_wichaa: {n} pictures staged as cas/<sha256> → R2 {BUCKET}/{PREFIX}")
            cmd = [py, str(R2_PUT_TREE), tmp, BUCKET, PREFIX] + (["--dry-run"] if a.dry_run else [])
            r = subprocess.run(cmd, env={**os.environ, "CLOUDFLARE_API_TOKEN": tok})
            if r.returncode:
                print("export_wichaa: R2 upload failed; aborting so no page ships with missing pictures")
                return r.returncode

    out = docs / "amulets"
    env = {**os.environ, "SITE_URL": f"{site_url}/amulets", "IMAGE_BASE": f"{site_url}/img", "CARDS_DIR": str(CARDS)}
    r = subprocess.run([py, str(here / "site.py")], env=env)
    if r.returncode:
        return r.returncode
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(BUILD / "site", out)
    # the search page fetches the meaning half from /api/search on the wichaa host; the
    # static copy never needs a server, so nothing else changes
    n_html = sum(1 for _ in out.rglob("*.html"))
    print(f"export_wichaa: {n_html} pages → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
