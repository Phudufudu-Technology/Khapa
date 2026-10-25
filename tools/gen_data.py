"""Generate src/khapa_core/data.py from the prototype's data.js (via tools/dump_data.js).

Content is generated, not retyped, so the port cannot drift from the prototype.
Run:  node tools/dump_data.js > /tmp/data.json && python tools/gen_data.py /tmp/data.json
"""
import json
import pprint
import sys
from pathlib import Path

src = json.load(open(sys.argv[1], encoding="utf-8"))
out = Path(__file__).resolve().parent.parent / "src" / "khapa_core" / "data.py"

lines = [
    '"""Synthetic content for the Khapa demo. Every learner and teacher here is fictional.',
    "",
    "GENERATED from tools/reference/data.js by tools/gen_data.py. Do not edit by hand:",
    "re-run the generator so the port stays faithful to the prototype.",
    '"""',
    "",
    "from __future__ import annotations",
    "",
]
for key in src:
    body = pprint.pformat(src[key], width=100, sort_dicts=False)
    lines.append(f"{key} = {body}")
    lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, out.stat().st_size, "bytes")
