#!/usr/bin/env python3
"""Regenerates guns/<NAME>/<NAME>.ino from mark_fx.ino. Run again after any firmware change."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GUNS = [f"BLUE{i}" for i in range(1, 5)] + [f"RED{i}" for i in range(1, 5)]
LINE = "#define GUN BLUE1\n"

with open(os.path.join(HERE, "mark_fx.ino")) as f:
    source = f.read()
if source.count(LINE) != 1:
    raise SystemExit("Could not find the GUN line in mark_fx.ino")

for name in GUNS:
    folder = os.path.join(HERE, "..", "guns", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ".ino"), "w") as f:
        f.write(source.replace(LINE, f"#define GUN {name}\n"))
    print("wrote", name)
