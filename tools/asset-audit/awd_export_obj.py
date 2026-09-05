#!/usr/bin/env python3
"""awd_export_obj - AWD -> OBJ keeping DarkOrbit's own object names.

Unlike the reference awd2obj.py this one:
  * keeps one `o <object>` group per render object (so Blender shows the same
    part breakdown the original artist worked with);
  * drops the invisible locator boxes (laserpoint_*, engine_*, light_position)
    into a separate `--anchors` file instead of mixing them with the hull;
  * writes a sidecar .json with the object -> triangle-range map so the render
    tool can colour parts.

Axes: AWD/Away3D is left-handed Y-up; Z is mirrored and winding flipped so the
result reads correctly in Blender/Godot.

    py awd_export_obj.py in.awd out.obj [--anchors]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

from audit_awd import is_anchor
from awd_reader import read_awd


def export(path_in, path_out, keep_anchors=False):
    doc = read_awd(path_in)
    geo = {g.block_id: g for g in doc.geometries}
    mats = {m.block_id: m.name.replace("null~", "") for m in doc.materials}

    groups = []
    used = set()
    for me in doc.meshes:
        g = geo.get(me.geometry_id)
        if g is None:
            continue
        used.add(g.block_id)
        tris = sum(len(s.indices) // 3 for s in g.subs)
        if is_anchor(me.name, tris) and not keep_anchors:
            continue
        groups.append((me.name or g.name or "part",
                       [mats[i] for i in me.material_ids if i in mats], g))
    for g in doc.geometries:
        if g.block_id not in used and sum(len(s.indices) for s in g.subs):
            groups.append((g.name or "orphan", [], g))

    base_v = base_t = 1
    index = []
    tri_cursor = 0
    with open(path_out, "w", encoding="utf-8") as f:
        f.write(f"# {os.path.basename(path_in)} via awd_export_obj\n")
        for name, mnames, g in groups:
            for si, s in enumerate(g.subs):
                if not s.positions or not s.indices:
                    continue
                P = np.array(s.positions, float).reshape(-1, 3)
                I = np.array(s.indices, np.int64).reshape(-1, 3)
                U = (np.array(s.uv0, float).reshape(-1, 2)
                     if len(s.uv0) // 2 == len(P) else None)
                gname = name if len(g.subs) == 1 else f"{name}.{si}"
                f.write(f"o {gname}\n")
                if mnames:
                    f.write(f"usemtl {mnames[0]}\n")
                for x, y, z in P:
                    f.write(f"v {x:.5f} {y:.5f} {-z:.5f}\n")
                if U is not None:
                    for u, v in U:
                        f.write(f"vt {u:.5f} {1.0-v:.5f}\n")
                for a, b, c in I:
                    A, B, C = a + base_v, b + base_v, c + base_v
                    if U is not None:
                        f.write(f"f {A}/{a+base_t} {C}/{c+base_t} {B}/{b+base_t}\n")
                    else:
                        f.write(f"f {A} {C} {B}\n")
                index.append({"object": gname, "material": mnames[0] if mnames else "",
                              "tri_start": tri_cursor, "tris": len(I),
                              "verts": len(P), "has_uv": U is not None})
                tri_cursor += len(I)
                base_v += len(P)
                base_t += len(U) if U is not None else 0
    with open(os.path.splitext(path_out)[0] + ".parts.json", "w",
              encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    return tri_cursor, len(index)


if __name__ == "__main__":
    keep = "--anchors" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    t, n = export(args[0], args[1], keep)
    print(f"OK -> {args[1]}  ({n} objetos, {t} tris)")
