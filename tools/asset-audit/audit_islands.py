#!/usr/bin/env python3
"""audit_islands - per-piece audit of an AWD corpus.

DarkOrbit models are assemblies: one "object" in the file is usually dozens of
disconnected pieces that merely intersect. This walks every piece of every
asset and records its size, whether it is closed, whether it is a flat card,
and — the point of the exercise — how many segments a round piece was built
with.

    py audit_islands.py <folder> out.csv [--min-tris=6]
"""
from __future__ import annotations

import csv
import os
import sys
import time

from audit_awd import gather
from awd_reader import read_awd
from mesh_metrics import analyse_islands


def main():
    folder = sys.argv[1]
    out_csv = sys.argv[2]
    min_tris = 6
    for a in sys.argv[3:]:
        if a.startswith("--min-tris="):
            min_tris = int(a.split("=", 1)[1])

    rows = []
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".awd"))
    t0 = time.time()
    for i, f in enumerate(files, 1):
        try:
            doc = read_awd(os.path.join(folder, f))
            _objs, V, F, _U = gather(doc)
            if V is None:
                continue
            for r in analyse_islands(V, F, max_islands=80):
                if r["tris"] < min_tris:
                    continue
                r["asset"] = os.path.splitext(f)[0]
                rows.append(r)
        except Exception as exc:                                   # noqa: BLE001
            print(f"  !! {f}: {exc!r}")
        if i % 25 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] {time.time()-t0:.0f}s "
                  f"({len(rows)} piezas)", flush=True)

    keys = ["asset", "island", "tris", "verts", "diag", "size_share_of_asset",
            "flat_card", "closed", "boundary_edges", "rot_order", "rot_frac",
            "rot_axis", "radial_slots", "slot_regularity", "sphere_fit_rms_rel",
            "median_valence", "aspect", "size"]
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"OK -> {out_csv} ({len(rows)} piezas de {len(files)} assets)")


if __name__ == "__main__":
    main()
