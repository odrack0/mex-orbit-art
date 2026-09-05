#!/usr/bin/env python3
"""merge_report - one row per asset joining geometry, in-game scale and the
texture set that actually shipped.

    py merge_report.py out/meshes.csv out/textures.csv out/do_scales.json \
                       out/islands.csv assets.csv assets.json
"""
from __future__ import annotations

import collections
import csv
import json
import sys

# tex_settings -> texture edge in px at each quality level, read out of the
# client's Settings3D (LOW / MEDIUM / HIGH).
TEX_CLASS_PX = {
    "ship_very_small": (64, 64, 128), "ship_small": (64, 64, 128),
    "ship": (128, 128, 256), "ship_big": (256, 256, 512),
    "drone": (64, 64, 128), "building_small": (128, 256, 512),
    "building": (256, 512, 1024), "building_big": (1024, 1024, 1024),
    "planet": (256, 512, 1024), "planet_small": (128, 256, 512),
}

KEEP = [
    "asset", "role", "tris", "verts_stored", "verts_welded",
    "vertex_split_ratio", "edges", "islands", "render_objects",
    "anchor_objects", "materials", "largest_island_tri_share",
    "island_bbox_overlaps", "planar_islands", "open_shell", "boundary_edges",
    "nonmanifold_edges", "degenerate_tris", "duplicate_faces",
    "quads_detected", "quad_tri_ratio", "ngon_clusters_ge3",
    "hard_edges_gt30", "hard_edge_ratio", "mean_dihedral_deg",
    "stores_normals", "stores_uv", "has_skeleton", "vertex_anim_blocks",
    "uv_coverage", "uv_overlap_factor", "uv_tiled", "texel_density_iqr_ratio",
    "bbox_x", "bbox_y", "bbox_z", "bbox_diag", "flatness_ratio",
    "best_mirror", "best_mirror_frac",
    "tri_share_y_upper_half", "tri_share_outer_third_radial",
    "tris_visible_gamecam", "hidden_gamecam_ratio",
    "silhouette_band_tri_share", "tri_share_for_90pct_pixels",
    "tris_never_visible", "interior_tri_ratio",
    "game_scale", "px_per_unit", "screen_px_height", "subpixel_tri_ratio",
    "median_tri_px", "tex_settings", "tex_px_low", "tex_px_med", "tex_px_high",
    "tex_channels", "tex_files", "tex_max_px",
    "round_pieces", "round_segments_median", "round_segments_max",
    "sphere_pieces", "flat_pieces",
    "texels_per_tri_high", "object_names", "material_names",
]


def role_of(a, cls):
    if a.startswith("drone-") or a.endswith(("_drone", "-drone")):
        return "drone"
    if a.startswith("pet"):
        return "pet"
    if a.startswith(("building-", "cbs", "low-station", "boosterstation",
                     "streuner-homebase", "pirate-base", "module")):
        return "estructura"
    if a.startswith(("jumpgate", "galaxygate", "eventgate", "z-gate",
                     "streuner-gate", "beacon")):
        return "portal/baliza"
    if (a.startswith(("zone_", "cluster_", "iceBerg", "asset-", "ore-", "mine-",
                      "icecube", "i-oil", "ice-meteoroid", "skybox", "fx_sky",
                      "planet-")) or "asteroid" in a or "scrap" in a):
        return "ambiental"
    if a.startswith("_placeholder"):
        return "placeholder"
    return {"ship": "nave", "ship_small": "nave pequena",
            "ship_very_small": "nave muy pequena", "ship_big": "NPC/nave grande",
            "drone": "drone", "building": "estructura",
            "building_small": "estructura pequena",
            "building_big": "estructura grande",
            "planet": "ambiental"}.get(cls, "(no referenciado)")


def main():
    meshes, textures, scales_p, islands, out_csv, out_json = sys.argv[1:7]
    rows = {r["asset"]: dict(r)
            for r in csv.DictReader(open(meshes, encoding="utf-8"))}
    scales = json.load(open(scales_p, encoding="utf-8"))

    tex = collections.defaultdict(list)
    for r in csv.DictReader(open(textures, encoding="utf-8")):
        tex[r["asset"]].append(r)

    isl = collections.defaultdict(list)
    for r in csv.DictReader(open(islands, encoding="utf-8")):
        isl[r["asset"]].append(r)

    out = []
    for a, r in rows.items():
        if not float(r.get("tris") or 0):
            continue
        sc = scales.get(a, {})
        cls = sc.get("tex_settings", "")
        r["role"] = role_of(a, cls)
        lo, me, hi = TEX_CLASS_PX.get(cls, ("", "", ""))
        r["tex_px_low"], r["tex_px_med"], r["tex_px_high"] = lo, me, hi

        # the texture set is keyed by @texture when given, else by geometry name
        tkey = sc.get("texture") or a
        tl = tex.get(tkey) or tex.get(a) or []
        r["tex_channels"] = "+".join(sorted({t["channel"] for t in tl})) or ""
        r["tex_files"] = len(tl)
        r["tex_max_px"] = max((int(t["width"] or 0) for t in tl), default="")
        if hi and float(r["tris"]):
            r["texels_per_tri_high"] = round(hi * hi / float(r["tris"]), 1)

        bx, by, bz = (float(r.get(k) or 0) for k in ("bbox_x", "bbox_y", "bbox_z"))
        r["flatness_ratio"] = round(by / max(bx, bz, 1e-9), 3)

        pieces = isl.get(a, [])
        rnd = [int(p["rot_order"]) for p in pieces if int(p["rot_order"]) >= 3]
        r["round_pieces"] = len(rnd)
        r["round_segments_median"] = (sorted(rnd)[len(rnd) // 2] if rnd else "")
        r["round_segments_max"] = max(rnd) if rnd else ""
        r["sphere_pieces"] = sum(
            1 for p in pieces
            if float(p["sphere_fit_rms_rel"] or 1) < 0.06
            and float(p["aspect"] or 9) < 1.6 and int(p["tris"]) >= 40)
        r["flat_pieces"] = sum(1 for p in pieces if p["flat_card"] == "True")
        out.append(r)

    out.sort(key=lambda r: (r["role"], -float(r["tris"])))
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=KEEP, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump({"schema_note": "una fila por asset; px calculados con la "
                                  "camara documentada de DarkOrbit (FOV 30, "
                                  "d=1740, elev 45, azim 25) a 1080p y zoom 1",
                   "assets": [{k: r.get(k) for k in KEEP} for r in out]},
                  fh, indent=1)
    print(f"OK -> {out_csv} ({len(out)} assets, {len(KEEP)} columnas)")


if __name__ == "__main__":
    main()
