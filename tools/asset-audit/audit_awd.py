#!/usr/bin/env python3
"""audit_awd - corpus audit of a folder of AWD meshes.

Pass 1 (`--light`) runs cheap structural metrics on every file; the full run
adds the rasterised visibility work, which is the expensive part.

    py audit_awd.py <folder> out.csv out.json [--light] [--only name1,name2]

Anchor detection: DarkOrbit ships carry invisible locator objects (weapon
muzzles, engine nozzles, light positions) exported as tiny 8-triangle boxes.
They are counted separately so they never pollute the art budget.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

import numpy as np

from awd_reader import read_awd
from mesh_metrics import analyse

ANCHOR_PREFIXES = ("laserpoint", "engine", "light_position", "rocketpoint",
                   "weaponpoint", "hitpoint", "nozzle", "muzzle", "anchor",
                   "flare", "socket")


def is_anchor(obj_name: str, tris: int) -> bool:
    n = (obj_name or "").lower()
    return tris <= 12 and any(n.startswith(p) for p in ANCHOR_PREFIXES)


def gather(doc):
    """Return (objects, merged V/F/UV/N) with anchors flagged."""
    geo = {g.block_id: g for g in doc.geometries}
    mats = {m.block_id: m for m in doc.materials}
    objs = []
    Vs, Fs, Us, base = [], [], [], 0
    used_geo = set()
    for me in doc.meshes:
        g = geo.get(me.geometry_id)
        if g is None:
            continue
        used_geo.add(g.block_id)
        tris = sum(len(s.indices) // 3 for s in g.subs)
        verts = sum(len(s.positions) // 3 for s in g.subs)
        anchor = is_anchor(me.name, tris)
        objs.append({
            "obj": me.name, "geo": g.name, "tris": tris, "verts": verts,
            "subs": len(g.subs), "anchor": anchor,
            "streams": sorted({t for s in g.subs for t in s.streams}),
            "mats": [mats[i].name for i in me.material_ids if i in mats],
        })
        if anchor:
            continue
        for s in g.subs:
            if not s.positions or not s.indices:
                continue
            P = np.array(s.positions, float).reshape(-1, 3)
            I = np.array(s.indices, np.int64).reshape(-1, 3)
            U = (np.array(s.uv0, float).reshape(-1, 2)
                 if len(s.uv0) // 2 == len(P) else np.zeros((len(P), 2)))
            Vs.append(P); Fs.append(I + base); Us.append(U)
            base += len(P)
    # geometries never instanced by a mesh block (orphans) still count as data
    for g in doc.geometries:
        if g.block_id in used_geo:
            continue
        tris = sum(len(s.indices) // 3 for s in g.subs)
        if tris == 0:
            continue
        objs.append({"obj": f"<orphan:{g.name}>", "geo": g.name, "tris": tris,
                     "verts": sum(len(s.positions) // 3 for s in g.subs),
                     "subs": len(g.subs), "anchor": False,
                     "streams": sorted({t for s in g.subs for t in s.streams}),
                     "mats": []})
        for s in g.subs:
            if not s.positions or not s.indices:
                continue
            P = np.array(s.positions, float).reshape(-1, 3)
            I = np.array(s.indices, np.int64).reshape(-1, 3)
            U = (np.array(s.uv0, float).reshape(-1, 2)
                 if len(s.uv0) // 2 == len(P) else np.zeros((len(P), 2)))
            Vs.append(P); Fs.append(I + base); Us.append(U)
            base += len(P)
    if not Vs:
        return objs, None, None, None
    return objs, np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Us)


def audit_file(path, heavy=True, px_per_unit=None):
    doc = read_awd(path)
    objs, V, F, U = gather(doc)
    name = os.path.splitext(os.path.basename(path))[0]
    anchors = [o for o in objs if o["anchor"]]
    real = [o for o in objs if not o["anchor"]]
    row = {
        "asset": name,
        "file_kb": round(os.path.getsize(path) / 1024, 1),
        "awd_version": f"{doc.version[0]}.{doc.version[1]}",
        "compressed": doc.compression,
        "geometry_blocks": len(doc.geometries),
        "mesh_objects": len(doc.meshes),
        "render_objects": len(real),
        "anchor_objects": len(anchors),
        "anchor_tris": sum(o["tris"] for o in anchors),
        "materials": len(doc.materials),
        "material_names": "|".join(sorted({m.name.replace("null~", "")
                                           for m in doc.materials})),
        "object_names": "|".join(o["obj"] for o in real),
        "has_skeleton": doc.skeletons > 0,
        "vertex_anim_blocks": doc.vertex_anim_blocks,
        "embedded_textures": len(doc.textures),
        "stream_types": "|".join(str(s) for s in sorted(
            {s for o in objs for s in o["streams"]})),
        "stores_normals": 4 in {s for o in objs for s in o["streams"]},
        "stores_uv": 3 in {s for o in objs for s in o["streams"]},
        "stores_uv1": 5 in {s for o in objs for s in o["streams"]},
        "stores_skin": 6 in {s for o in objs for s in o["streams"]},
    }
    if V is None:
        row["tris"] = 0
        return row, objs
    m = analyse(V, F, U, None, name=name, heavy=heavy, px_per_unit=px_per_unit)
    m.pop("_rot_table", None)
    m.pop("name", None)
    row.update(m)
    return row, objs


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    folder, out_csv, out_json = args[0], args[1], args[2]
    heavy = "--light" not in flags
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = set(a.split("=", 1)[1].split(","))
    ppu = None
    for a in sys.argv[1:]:
        if a.startswith("--px-per-unit="):
            ppu = float(a.split("=", 1)[1])
    scales = {}
    for a in sys.argv[1:]:
        if a.startswith("--scales="):
            scales = json.load(open(a.split("=", 1)[1], encoding="utf-8"))

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".awd"))
    if only:
        files = [f for f in files if os.path.splitext(f)[0] in only]
    rows, details = [], {}
    t0 = time.time()
    for i, f in enumerate(files, 1):
        p = os.path.join(folder, f)
        stem = os.path.splitext(f)[0]
        sc = scales.get(stem)
        px = sc["px_per_unit_zoom1"] if sc else ppu
        try:
            row, objs = audit_file(p, heavy=heavy, px_per_unit=px)
        except Exception as exc:                                   # noqa: BLE001
            print(f"  !! {f}: {exc!r}")
            continue
        if sc:
            row.update(game_scale=sc["scale_median"],
                       tex_settings=sc["tex_settings"],
                       tex_high_px=sc["tex_high_px"],
                       texture_id=sc["texture"],
                       px_per_unit=px)
        rows.append(row)
        details[row["asset"]] = objs
        if i % 10 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] {f}  ({time.time()-t0:.0f}s)")
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "objects": details}, fh, indent=1)
    print(f"OK -> {out_csv} / {out_json}  ({len(rows)} assets, "
          f"{time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
