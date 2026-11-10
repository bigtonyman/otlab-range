#!/usr/bin/env python3
"""Copy the upstream simulators tree and switch every simulator's logging off (otlab: no OpenSearch, no log volume).
usage: prep_sims.py <upstream simulators dir> <output dir>"""
import json, pathlib, shutil, sys

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
n = 0
for f in sorted((dst / "flamingmoes").glob("*.json")):
    d = json.loads(f.read_text())
    for v in d.values():
        if isinstance(v, dict) and isinstance(v.get("logging"), dict) and v["logging"].get("logging"):
            v["logging"]["logging"] = False
            n += 1
    f.write_text(json.dumps(d, indent=2) + "\n")
print(f"logging disabled in {n} simulator entries")
