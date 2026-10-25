#!/usr/bin/env bash
# One command for judges and for you (macOS/Linux): creates the venv on first run, installs pinned Flet, starts Khapa.
#   ./run_demo.sh          desktop window
#   ./run_demo.sh web      browser at http://localhost:8550
#   ./run_demo.sh phone    desktop window sized like a phone
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ "${1:-}" = "phone" ] && export KHAPA_PREVIEW_PHONE=1
if [ "${1:-}" = "web" ]; then flet run --web --port 8550 src/main.py; else flet run src/main.py; fi
