#!/bin/bash
# Double-click this file to run the amulet catalogue pipeline from a numbered menu.
P="$(cd "$(dirname "$0")" && pwd)"
cd "$P" || { echo "Project folder not found: $P"; read -p "Press return to close."; exit 1; }
PY=python3
[ -x "$P/.venv/bin/python" ] && PY="$P/.venv/bin/python"

while true; do
  echo
  echo "AMULET ESSENTIALS"
  echo "  1  Validate every record"
  echo "  2  Build (validate + API + database + search tables)"
  echo "  3  Embed (meaning vectors, local model)"
  echo "  4  Make the website (build/site)"
  echo "  5  Everything: 1-4 then open the site"
  echo "  6  Search (type a question in Thai or English)"
  echo "  7  Run the tests"
  echo "  8  Serve the site with live meaning search (http://127.0.0.1:8793)"
  echo "  9  Harvest free images from Commons for every record"
  echo " 10  Build the picture index (photo identification)"
  echo " 11  Identify a photo (drag the file into this window, then return)"
  echo "  0  Quit"
  read -p "Number: " n
  case "$n" in
    1) $PY tools/validate.py ;;
    2) $PY tools/build.py ;;
    3) $PY tools/embed.py ;;
    4) $PY tools/site.py ;;
    5) $PY tools/build.py && $PY tools/embed.py; $PY tools/vision.py --build; $PY tools/site.py && open "build/site/index.html" ;;
    6) read -p "Search: " q; $PY tools/search.py "$q" ;;
    7) $PY -m unittest discover -s tests -v 2>&1 | tail -25 ;;
    8) $PY tools/serve.py ;;
    9) $PY tools/harvest_commons.py --harvest --apply ;;
    10) $PY tools/vision.py --build ;;
    11) read -p "Photo path: " f; $PY tools/vision.py "${f%% }" ;;
    0) exit 0 ;;
    *) echo "Pick a number." ;;
  esac
done
