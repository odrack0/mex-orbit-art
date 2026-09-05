#!/usr/bin/env python3
"""render_silhouette_map - where does a mesh spend its triangles, relative to
the gameplay silhouette?

Rasterises the mesh from the real DarkOrbit camera and paints every triangle by
its role:

    red     touches the outer silhouette band  -> pays for the outline
    blue    visible but interior to the outline -> pays for surface shading
    grey    facing away / occluded in this view -> pays for nothing here

A second panel shows the same mesh scaled to the pixel size it really has in
game, so the reader can judge whether any of it was worth modelling.

    py render_silhouette_map.py out_dir asset1.obj asset2.obj ...
    py render_silhouette_map.py out_dir --awd folder name1 name2 ...
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt

from mesh_metrics import (GAME_CAM_AZIMUTH_DEG, GAME_CAM_ELEVATION_DEG,
                          _basis, camera_dir, load_obj)

BAND_PX = 4


def raster(V, F, direction, res):
    """Depth-buffered id buffer plus per-triangle shading term."""
    u, v, w = _basis(np.asarray(direction, float))
    P = np.stack([V @ u, V @ v, V @ w], axis=1)
    lo = P[:, :2].min(axis=0); hi = P[:, :2].max(axis=0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1])) or 1.0
    scale = (res - 6) / span
    off = (np.array([res, res]) - (hi - lo) * scale) / 2.0
    S = (P[:, :2] - lo) * scale + off
    Z = P[:, 2]
    zbuf = np.full((res, res), np.inf)
    ibuf = np.full((res, res), -1, np.int32)
    a, b, c = S[F[:, 0]], S[F[:, 1]], S[F[:, 2]]
    za, zb, zc = Z[F[:, 0]], Z[F[:, 1]], Z[F[:, 2]]
    for t in range(len(F)):
        ax, ay = a[t]; bx, by = b[t]; cx, cy = c[t]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-12:
            continue
        x0 = max(int(np.floor(min(ax, bx, cx))), 0)
        x1 = min(int(np.ceil(max(ax, bx, cx))), res - 1)
        y0 = max(int(np.floor(min(ay, by, cy))), 0)
        y1 = min(int(np.ceil(max(ay, by, cy))), res - 1)
        if x1 < x0 or y1 < y0:
            continue
        px, py = np.meshgrid(np.arange(x0, x1 + 1) + .5,
                             np.arange(y0, y1 + 1) + .5)
        w0 = ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / area
        w1 = ((cx - bx) * (py - by) - (cy - by) * (px - bx)) / area
        w2 = 1.0 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not m.any():
            continue
        z = w1 * za[t] + w2 * zb[t] + w0 * zc[t]
        sz = zbuf[y0:y1 + 1, x0:x1 + 1]; si = ibuf[y0:y1 + 1, x0:x1 + 1]
        upd = m & (z < sz)
        sz[upd] = z[upd]; si[upd] = t
    return ibuf


def shade(V, F, direction):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-20)[:, None]
    key = -np.asarray(direction, float)
    lamb = np.clip(n @ (key / np.linalg.norm(key)), 0, 1)
    return 0.35 + 0.65 * lamb


def colourise(ibuf, F_count, tone):
    mask = ibuf >= 0
    img = np.full(ibuf.shape + (3,), 26, np.uint8)
    if not mask.any():
        return img, np.zeros(F_count, bool), np.zeros(F_count, bool)
    dist = distance_transform_edt(mask)
    band = mask & (dist <= BAND_PX)
    on_edge = np.zeros(F_count, bool)
    ids = ibuf[band]; on_edge[ids[ids >= 0]] = True
    visible = np.zeros(F_count, bool)
    idv = ibuf[mask]; visible[idv[idv >= 0]] = True
    idx = np.where(mask)
    tri = ibuf[idx]
    base = np.where(on_edge[tri][:, None],
                    np.array([232, 78, 62]), np.array([70, 130, 220]))
    img[idx] = np.clip(base * tone[tri][:, None], 0, 255).astype(np.uint8)
    return img, visible, on_edge


def font(sz=16):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def process(V, F, name, out_dir, px_per_unit=None, res=560):
    d = camera_dir(GAME_CAM_ELEVATION_DEG, GAME_CAM_AZIMUTH_DEG)
    tone = shade(V, F, d)
    ib = raster(V, F, d, res)
    img, visible, on_edge = colourise(ib, len(F), tone)

    game_px = None
    if px_per_unit:
        size = float(np.linalg.norm(V.max(0) - V.min(0)))
        game_px = max(16, int(round(size * px_per_unit)))
        ib2 = raster(V, F, d, game_px)
        img2, _, _ = colourise(ib2, len(F), tone)
    else:
        img2 = None

    stats = {
        "tris": len(F),
        "visible": int(visible.sum()),
        "on_silhouette": int(on_edge.sum()),
        "hidden": int(len(F) - visible.sum()),
        "silhouette_share_of_visible": round(
            float(on_edge.sum() / max(visible.sum(), 1)), 3),
        "hidden_share": round(float(1 - visible.mean()), 3),
        "game_px": game_px,
    }

    W = res + (res if img2 is not None else 0) + 30
    sheet = Image.new("RGB", (W, res + 78), (18, 18, 22))
    sheet.paste(Image.fromarray(img), (10, 62))
    if img2 is not None:
        big = Image.fromarray(img2).resize((res, res), Image.NEAREST)
        sheet.paste(big, (res + 20, 62))
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 8), f"{name} — {len(F)} tris", fill=(240, 240, 245), font=font(20))
    dr.text((10, 34),
            f"rojo = toca la silueta ({stats['silhouette_share_of_visible']:.0%} "
            f"de los visibles) · azul = interior visible · "
            f"oculto en esta vista: {stats['hidden_share']:.0%}",
            fill=(180, 180, 190), font=font(15))
    dr.text((10, res + 64), "vista de diagnostico (560 px)",
            fill=(150, 150, 160), font=font(14))
    if img2 is not None:
        dr.text((res + 20, res + 64),
                f"mismo mesh al tamano REAL de juego: {game_px} px "
                f"(ampliado sin filtrar)", fill=(150, 150, 160), font=font(14))
    p = os.path.join(out_dir, f"sil_{name}.png")
    sheet.save(p)
    return p, stats


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    import json
    scales = {}
    args = sys.argv[2:]
    if args and args[0].startswith("--scales="):
        scales = json.load(open(args[0].split("=", 1)[1], encoding="utf-8"))
        args = args[1:]
    allstats = {}
    for p in args:
        name = os.path.splitext(os.path.basename(p))[0]
        V, F, U, N = load_obj(p)
        ppu = scales.get(name, {}).get("px_per_unit_zoom1")
        out, st = process(V, F, name, out_dir, ppu)
        allstats[name] = st
        print(f"{out}  {st}")
    with open(os.path.join(out_dir, "_silhouette_stats.json"), "w") as f:
        json.dump(allstats, f, indent=1)


if __name__ == "__main__":
    main()
