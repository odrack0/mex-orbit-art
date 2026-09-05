#!/usr/bin/env python3
"""mesh_metrics - format-agnostic low-poly audit for top-down space game assets.

Takes raw arrays (positions, triangles, uvs, normals) and answers the questions
that matter for a top-down/oblique camera:

  * how much geometry exists, and how much of it is *welded* vs split;
  * topology: quad pairs, coplanar clusters (n-gon intent), hard edges,
    boundary (open shell) edges, non-manifold edges, connected islands;
  * are islands welded to each other or merely intersected;
  * symmetry: mirror planes and rotational order (= segment count of a
    cylinder / ring / sphere), measured, not guessed;
  * where the triangles physically are (top vs bottom, core vs rim);
  * how many triangles ever reach the screen from the real game camera, and
    how many of them sit on the silhouette edge.

Everything is pure numpy + scipy, so it runs on AWD, OBJ and GLB alike.

The same module is meant to be pointed at Astrion's own GLB assets later:
    py mesh_metrics.py model.glb
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

# Real DarkOrbit gameplay camera, reverse-engineered in
# mex-orbit-docs/03-guidelines/darkorbit-3d/camara-proyeccion.md:
# perspective FOV 30 deg, pivot on the ship, elevation 45 deg (tilt 135),
# azimuth (pan) 25 deg on 3D maps. At max zoom-in elevation drops to ~25 deg.
GAME_CAM_ELEVATION_DEG = 45.0
GAME_CAM_AZIMUTH_DEG = 25.0
GAME_CAM_ZOOMED_ELEVATION_DEG = 25.0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def camera_dir(elevation_deg: float, azimuth_deg: float) -> np.ndarray:
    """Unit view direction (camera -> target) in a Y-up frame."""
    el = math.radians(elevation_deg)
    az = math.radians(azimuth_deg)
    eye = np.array([math.sin(az) * math.cos(el),
                    math.sin(el),
                    math.cos(az) * math.cos(el)])
    return -eye / np.linalg.norm(eye)


def _basis(d: np.ndarray):
    d = d / np.linalg.norm(d)
    up = np.array([0.0, 1.0, 0.0])
    if abs(np.dot(d, up)) > 0.99:
        up = np.array([1.0, 0.0, 0.0])
    u = np.cross(up, d)
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    return u, v, d


def _sphere_dirs(n: int = 26) -> np.ndarray:
    """Roughly uniform directions on a sphere (Fibonacci)."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi),
                     np.cos(phi),
                     np.sin(theta) * np.sin(phi)], axis=1)


class UnionFind:
    def __init__(self, n):
        self.p = np.arange(n)

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _labels(uf: UnionFind, n: int):
    roots = np.array([uf.find(i) for i in range(n)])
    _, lab = np.unique(roots, return_inverse=True)
    return lab


# --------------------------------------------------------------------------- #
# rasterised visibility
# --------------------------------------------------------------------------- #
def visible_triangle_area(V, F, direction, res=384):
    """Orthographic z-buffer. Returns (visible_px_per_tri, id_buffer, extent).

    Visible pixel counts are a proxy for on-screen contribution: a triangle
    with 0 visible pixels never reaches the player's eye from that direction.
    """
    u, v, w = _basis(np.asarray(direction, float))
    P = np.stack([V @ u, V @ v, V @ w], axis=1)
    lo = P[:, :2].min(axis=0)
    hi = P[:, :2].max(axis=0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1])) or 1.0
    scale = (res - 4) / span
    S = (P[:, :2] - lo) * scale + 2.0
    Z = P[:, 2]

    zbuf = np.full((res, res), np.inf)
    ibuf = np.full((res, res), -1, dtype=np.int32)

    a, b, c = S[F[:, 0]], S[F[:, 1]], S[F[:, 2]]
    za, zb, zc = Z[F[:, 0]], Z[F[:, 1]], Z[F[:, 2]]
    x0 = np.floor(np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0])).astype(int)
    x1 = np.ceil(np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0])).astype(int)
    y0 = np.floor(np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1])).astype(int)
    y1 = np.ceil(np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1])).astype(int)
    np.clip(x0, 0, res - 1, out=x0); np.clip(x1, 0, res - 1, out=x1)
    np.clip(y0, 0, res - 1, out=y0); np.clip(y1, 0, res - 1, out=y1)

    for t in range(F.shape[0]):
        ax, ay = a[t]; bx, by = b[t]; cx, cy = c[t]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-12:
            continue
        xs = np.arange(x0[t], x1[t] + 1)
        ys = np.arange(y0[t], y1[t] + 1)
        if xs.size == 0 or ys.size == 0:
            continue
        px, py = np.meshgrid(xs + 0.5, ys + 0.5)
        w0 = ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / area
        w1 = ((cx - bx) * (py - by) - (cy - by) * (px - bx)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        # barycentric order: w1->A, w2->B, w0->C  (matches the edge functions)
        z = w1 * za[t] + w2 * zb[t] + w0 * zc[t]
        sub_z = zbuf[y0[t]:y1[t] + 1, x0[t]:x1[t] + 1]
        sub_i = ibuf[y0[t]:y1[t] + 1, x0[t]:x1[t] + 1]
        upd = inside & (z < sub_z)
        sub_z[upd] = z[upd]
        sub_i[upd] = t

    counts = np.bincount(ibuf[ibuf >= 0].ravel(), minlength=F.shape[0])
    return counts, ibuf, span


def silhouette_band_share(ibuf, F_count, band_px=3):
    """Share of visible triangles whose pixels touch the outer silhouette band."""
    from scipy.ndimage import distance_transform_edt
    mask = ibuf >= 0
    if not mask.any():
        return 0.0, np.zeros(F_count, bool)
    dist = distance_transform_edt(mask)
    band = mask & (dist <= band_px)
    on_edge = np.zeros(F_count, bool)
    ids = ibuf[band]
    on_edge[ids[ids >= 0]] = True
    visible = np.zeros(F_count, bool)
    idv = ibuf[mask]
    visible[idv[idv >= 0]] = True
    return (on_edge.sum() / max(visible.sum(), 1)), on_edge


# --------------------------------------------------------------------------- #
# main analysis
# --------------------------------------------------------------------------- #
def projected_px_area(V, F, direction, px_per_unit):
    """Analytic per-triangle projected area in px^2 (no occlusion, no culling)."""
    u, v, _ = _basis(np.asarray(direction, float))
    S = np.stack([V @ u, V @ v], axis=1) * px_per_unit
    a, b, c = S[F[:, 0]], S[F[:, 1]], S[F[:, 2]]
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) -
                        (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


def analyse(V, F, UV=None, N=None, name="", heavy=True, res=384, px_per_unit=None):
    """V:(n,3) F:(m,3) UV:(n,2)|None N:(n,3)|None -> dict of metrics."""
    V = np.asarray(V, dtype=np.float64).reshape(-1, 3)
    F = np.asarray(F, dtype=np.int64).reshape(-1, 3)
    out = {"name": name}

    lo, hi = V.min(axis=0), V.max(axis=0)
    dim = hi - lo
    diag = float(np.linalg.norm(dim)) or 1.0
    out.update(bbox_x=float(dim[0]), bbox_y=float(dim[1]), bbox_z=float(dim[2]),
               bbox_diag=diag)

    # ---- weld ------------------------------------------------------------- #
    eps = diag * 1e-5
    key = np.round(V / max(eps, 1e-12)).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    Vw = V[first]
    nv_stored, nv_weld = len(V), len(Vw)
    out.update(verts_stored=nv_stored, verts_welded=nv_weld,
               vertex_split_ratio=round(nv_stored / max(nv_weld, 1), 3))

    Fw = inv[F]
    good = (Fw[:, 0] != Fw[:, 1]) & (Fw[:, 1] != Fw[:, 2]) & (Fw[:, 0] != Fw[:, 2])
    out["tris"] = int(len(F))
    out["degenerate_tris"] = int((~good).sum())

    # duplicate faces (same welded triple)
    fsorted = np.sort(Fw[good], axis=1)
    _, fcnt = np.unique(fsorted, axis=0, return_counts=True)
    out["duplicate_faces"] = int((fcnt - 1).sum())

    Fg = Fw[good]
    if len(Fg) == 0:
        return out

    # ---- edges ------------------------------------------------------------ #
    E = np.concatenate([Fg[:, [0, 1]], Fg[:, [1, 2]], Fg[:, [2, 0]]], axis=0)
    E = np.sort(E, axis=1)
    Eu, einv, ecnt = np.unique(E, axis=0, return_inverse=True, return_counts=True)
    einv = einv.ravel()
    out.update(edges=int(len(Eu)),
               boundary_edges=int((ecnt == 1).sum()),
               nonmanifold_edges=int((ecnt > 2).sum()))
    out["open_shell"] = bool(out["boundary_edges"] > 0)
    out["euler_chi"] = int(nv_weld - len(Eu) + len(Fg))

    # ---- face normals, dihedral angles ------------------------------------ #
    p0, p1, p2 = Vw[Fg[:, 0]], Vw[Fg[:, 1]], Vw[Fg[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    farea = 0.5 * np.linalg.norm(cross, axis=1)
    fn = cross / np.maximum(np.linalg.norm(cross, axis=1), 1e-20)[:, None]
    out["surface_area"] = float(farea.sum())

    face_of_edge = np.repeat(np.arange(len(Fg)), 1)
    fid = np.tile(np.arange(len(Fg)), 3)
    order = np.argsort(einv, kind="stable")
    einv_s, fid_s = einv[order], fid[order]
    starts = np.searchsorted(einv_s, np.arange(len(Eu)))
    pair_mask = ecnt == 2
    idx = np.where(pair_mask)[0]
    fa = fid_s[starts[idx]]
    fb = fid_s[starts[idx] + 1]
    dot = np.clip((fn[fa] * fn[fb]).sum(axis=1), -1, 1)
    ang = np.degrees(np.arccos(dot))
    out["manifold_edge_pairs"] = int(len(idx))
    out["hard_edges_gt30"] = int((ang > 30).sum())
    out["hard_edge_ratio"] = round(float((ang > 30).mean()) if len(ang) else 0.0, 3)
    out["mean_dihedral_deg"] = round(float(ang.mean()) if len(ang) else 0.0, 2)

    # ---- quads & coplanar clusters (n-gon intent) ------------------------- #
    coplanar = ang < 1.0
    # greedy pairing of coplanar tri pairs -> quads
    used = np.zeros(len(Fg), bool)
    quads = 0
    for k in np.where(coplanar)[0]:
        A, B = fa[k], fb[k]
        if not used[A] and not used[B]:
            used[A] = used[B] = True
            quads += 1
    out["quads_detected"] = int(quads)
    out["quad_tri_ratio"] = round(2 * quads / len(Fg), 3)
    out["tris_not_in_quad"] = int(len(Fg) - 2 * quads)

    uf_f = UnionFind(len(Fg))
    for k in np.where(coplanar)[0]:
        uf_f.union(int(fa[k]), int(fb[k]))
    flab = _labels(uf_f, len(Fg))
    sizes = np.bincount(flab)
    out["coplanar_clusters"] = int(len(sizes))
    out["max_coplanar_cluster_tris"] = int(sizes.max())
    out["ngon_clusters_ge3"] = int((sizes >= 3).sum())
    out["tris_in_flat_clusters_ge3"] = int(sizes[sizes >= 3].sum())

    # ---- islands ---------------------------------------------------------- #
    uf_v = UnionFind(nv_weld)
    for e in Eu:
        uf_v.union(int(e[0]), int(e[1]))
    vlab = _labels(uf_v, nv_weld)
    n_isl = int(vlab.max() + 1)
    out["islands"] = n_isl
    isl_of_face = vlab[Fg[:, 0]]
    isl_tris = np.bincount(isl_of_face, minlength=n_isl)
    out["largest_island_tri_share"] = round(float(isl_tris.max() / len(Fg)), 3)

    # planar islands (alpha cards / flat plates)
    planar = 0
    for i in range(n_isl):
        pts = Vw[vlab == i]
        if len(pts) < 3:
            continue
        cov = np.cov((pts - pts.mean(axis=0)).T)
        ev = np.linalg.eigvalsh(cov)
        if ev[-1] > 0 and ev[0] / ev[-1] < 1e-6:
            planar += 1
    out["planar_islands"] = planar

    # islands that overlap in space but share no vertices -> intersected, not welded
    if n_isl > 1:
        boxes = [(Vw[vlab == i].min(axis=0), Vw[vlab == i].max(axis=0))
                 for i in range(n_isl)]
        inter = 0
        for i in range(n_isl):
            for j in range(i + 1, n_isl):
                a0, a1 = boxes[i]; b0, b1 = boxes[j]
                if np.all(a0 <= b1 + eps) and np.all(b0 <= a1 + eps):
                    inter += 1
        out["island_bbox_overlaps"] = inter
    else:
        out["island_bbox_overlaps"] = 0

    # ---- UVs --------------------------------------------------------------- #
    if UV is not None and len(UV) == nv_stored:
        UV = np.asarray(UV, float).reshape(-1, 2)
        out["has_uv"] = True
        out.update(uv_min_u=float(UV[:, 0].min()), uv_max_u=float(UV[:, 0].max()),
                   uv_min_v=float(UV[:, 1].min()), uv_max_v=float(UV[:, 1].max()))
        out["uv_tiled"] = bool(UV.min() < -0.01 or UV.max() > 1.01)
        a, b, c = UV[F[:, 0]], UV[F[:, 1]], UV[F[:, 2]]
        uv_area = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) -
                               (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
        out["uv_area_sum"] = round(float(uv_area.sum()), 4)
        # occupancy grid to detect overlapped / mirrored islands
        g = 256
        grid = np.zeros((g, g), bool)
        for t in range(len(F)):
            tri = np.clip(np.stack([a[t], b[t], c[t]]) % 1.0, 0, 0.9999) * g
            x0i, y0i = np.floor(tri.min(axis=0)).astype(int)
            x1i, y1i = np.ceil(tri.max(axis=0)).astype(int)
            grid[y0i:max(y1i, y0i + 1), x0i:max(x1i, x0i + 1)] = True
        cover = grid.mean()
        out["uv_coverage"] = round(float(cover), 4)
        out["uv_overlap_factor"] = round(float(out["uv_area_sum"] / max(cover, 1e-6)), 2)
        # UV seams: mesh edges whose two faces disagree on uv
        seam = 0
        for k in idx:
            pass
        out["uv_seam_ratio"] = round(float(1.0 - nv_weld / max(nv_stored, 1)), 3)
        # texel density spread: uv area / world area per triangle
        w_area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]],
                                               V[F[:, 2]] - V[F[:, 0]]), axis=1)
        ok = w_area > 1e-9
        if ok.sum() > 3:
            dens = np.sqrt(uv_area[ok] / w_area[ok])
            out["texel_density_p50"] = round(float(np.median(dens)), 5)
            out["texel_density_iqr_ratio"] = round(
                float(np.percentile(dens, 75) / max(np.percentile(dens, 25), 1e-9)), 2)
    else:
        out["has_uv"] = False

    out["has_normals_stream"] = bool(N is not None and len(N) == nv_stored)

    # ---- symmetry ---------------------------------------------------------- #
    tree = cKDTree(Vw)
    tol = diag * 2e-3
    center = (lo + hi) / 2.0
    for ax, axis_name in enumerate("xyz"):
        for label, plane in (("0", 0.0), ("c", float(center[ax]))):
            M = Vw.copy()
            M[:, ax] = 2 * plane - M[:, ax]
            d, _ = tree.query(M, distance_upper_bound=tol)
            frac = float(np.isfinite(d).mean())
            out[f"mirror_{axis_name}{label}"] = round(frac, 3)
    out["best_mirror"] = max(
        (k for k in out if k.startswith("mirror_")), key=lambda k: out[k])
    out["best_mirror_frac"] = out[out["best_mirror"]]

    # ---- rotational symmetry (segment count of round shapes) --------------- #
    best_k, best_axis, best_frac = 0, "", 0.0
    rot_table = {}
    for ax, axis_name in enumerate("xyz"):
        axis_v = np.zeros(3); axis_v[ax] = 1.0
        P = Vw - center
        ks = []
        for k in range(3, 65):
            th = 2 * math.pi / k
            ca, sa = math.cos(th), math.sin(th)
            R = _rot(axis_v, ca, sa)
            d, _ = tree.query(P @ R.T + center, distance_upper_bound=tol)
            f = float(np.isfinite(d).mean())
            if f >= 0.90:
                ks.append((k, f))
        rot_table[axis_name] = ks
        if ks:
            k, f = max(ks, key=lambda t: t[0])
            if k > best_k:
                best_k, best_axis, best_frac = k, axis_name, f
    out["rot_sym_order"] = best_k
    out["rot_sym_axis"] = best_axis
    out["rot_sym_frac"] = round(best_frac, 3)
    out["_rot_table"] = rot_table

    # ---- where the geometry sits ------------------------------------------ #
    fc = (V[F[:, 0]] + V[F[:, 1]] + V[F[:, 2]]) / 3.0
    for ax, axis_name in enumerate("xyz"):
        rel = (fc[:, ax] - lo[ax]) / max(dim[ax], 1e-9)
        out[f"tri_share_{axis_name}_upper_half"] = round(float((rel > 0.5).mean()), 3)
    # radial: distance from the vertical (Y) axis, normalised
    r = np.linalg.norm(fc[:, [0, 2]] - center[[0, 2]], axis=1)
    rmax = max(r.max(), 1e-9)
    out["tri_share_outer_third_radial"] = round(float((r > 0.667 * rmax).mean()), 3)
    out["area_share_outer_third_radial"] = round(
        float(farea[(r[good] > 0.667 * rmax)].sum() / max(farea.sum(), 1e-9)), 3)

    if not heavy:
        return out

    # ---- visibility from the real game camera ----------------------------- #
    d_game = camera_dir(GAME_CAM_ELEVATION_DEG, GAME_CAM_AZIMUTH_DEG)
    counts, ibuf, span = visible_triangle_area(V, F, d_game, res=res)
    vis = counts > 0
    out["tris_visible_gamecam"] = int(vis.sum())
    out["tris_hidden_gamecam"] = int(len(F) - vis.sum())
    out["hidden_gamecam_ratio"] = round(float(1 - vis.mean()), 3)
    band, on_edge = silhouette_band_share(ibuf, len(F), band_px=3)
    out["silhouette_band_tri_share"] = round(float(band), 3)
    px_total = int(counts.sum())
    out["visible_px"] = px_total
    if px_total:
        out["px_per_visible_tri"] = round(px_total / max(vis.sum(), 1), 2)
        srt = np.sort(counts)[::-1]
        cum = np.cumsum(srt) / px_total
        out["tris_for_50pct_pixels"] = int(np.searchsorted(cum, 0.5) + 1)
        out["tris_for_90pct_pixels"] = int(np.searchsorted(cum, 0.9) + 1)
        out["tri_share_for_90pct_pixels"] = round(
            float(out["tris_for_90pct_pixels"] / len(F)), 3)

    # ---- triangles too small to ever paint a pixel ------------------------ #
    if px_per_unit:
        pa = projected_px_area(V, F, d_game, px_per_unit)
        out["screen_px_height"] = round(float(dim.max() * px_per_unit), 1)
        out["tris_under_1px"] = int((pa < 1.0).sum())
        out["tris_under_4px"] = int((pa < 4.0).sum())
        out["subpixel_tri_ratio"] = round(float((pa < 1.0).mean()), 3)
        out["median_tri_px"] = round(float(np.median(pa)), 2)

    # ---- truly interior geometry (invisible from every direction) --------- #
    # Caveat: this is a rasterised test, so triangles smaller than a pixel of
    # the 256^2 probe can be reported as hidden even when they are not
    # occluded. Cross-read it with subpixel_tri_ratio.
    seen = np.zeros(len(F), bool)
    for d in _sphere_dirs(18):
        c2, _, _ = visible_triangle_area(V, F, d, res=256)
        seen |= c2 > 0
    out["tris_never_visible"] = int((~seen).sum())
    out["interior_tri_ratio"] = round(float((~seen).mean()), 3)
    return out


def rotational_order(P, axis, center, tol, kmax=64, thresh=0.90):
    """Largest k in [3,kmax] for which rotating P by 2*pi/k around `axis`
    maps the point set onto itself. That k is the segment count of a
    cylinder / ring / disc / sphere. Returns (k, match_fraction)."""
    if len(P) < 6:
        return 0, 0.0
    axis = np.asarray(axis, float)
    axis = axis / (np.linalg.norm(axis) or 1.0)
    tree = cKDTree(P)
    Q = P - center
    # Guard against the degenerate case that makes every k "match": points that
    # sit on (or very near) the rotation axis barely move when rotated.
    perp = Q - np.outer(Q @ axis, axis)
    if np.median(np.linalg.norm(perp, axis=1)) < 8.0 * tol:
        return 0, 0.0
    # A k-fold ring needs at least k points around it; anything else is noise.
    kmax = min(kmax, len(P) // 2)
    if kmax < 3:
        return 0, 0.0
    best = (0, 0.0)
    for k in range(3, kmax + 1):
        th = 2 * math.pi / k
        R = _rot(axis, math.cos(th), math.sin(th))
        d, _ = tree.query(Q @ R.T + center, distance_upper_bound=tol)
        f = float(np.isfinite(d).mean())
        if f >= thresh and k > best[0]:
            best = (k, f)
    return best


def fit_sphere(P):
    """Algebraic sphere fit. Returns (center, radius, rms/radius)."""
    A = np.hstack([2 * P, np.ones((len(P), 1))])
    b = (P ** 2).sum(axis=1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = sol[:3]
    r2 = sol[3] + (c ** 2).sum()
    if r2 <= 0:
        return c, 0.0, 1.0
    r = math.sqrt(r2)
    d = np.linalg.norm(P - c, axis=1)
    return c, r, float(np.sqrt(((d - r) ** 2).mean()) / max(r, 1e-9))


def radial_slots(P, axis, center, tol_deg=3.0):
    """How many distinct angular positions the points occupy around `axis`.

    For a lathed/extruded round part this is the segment count, and unlike
    rotational_order it survives caps, bevels and slightly irregular rings.
    """
    axis = np.asarray(axis, float)
    axis = axis / (np.linalg.norm(axis) or 1.0)
    Q = P - center
    Q = Q - np.outer(Q @ axis, axis)
    r = np.linalg.norm(Q, axis=1)
    keep = r > 0.05 * max(r.max(), 1e-9)
    if keep.sum() < 6:
        return 0, 0.0
    u, v, _ = _basis(axis)
    ang = np.degrees(np.arctan2(Q[keep] @ v, Q[keep] @ u)) % 360.0
    ang = np.sort(ang)
    slots = 1 + int((np.diff(ang) > tol_deg).sum())
    if ang[0] + 360 - ang[-1] <= tol_deg and slots > 1:
        slots -= 1
    # regularity: how evenly spaced those slots are
    reps = ang[np.concatenate([[True], np.diff(ang) > tol_deg])]
    if len(reps) > 2:
        gaps = np.diff(np.concatenate([reps, [reps[0] + 360]]))
        reg = float(1.0 - gaps.std() / max(gaps.mean(), 1e-9))
    else:
        reg = 0.0
    return slots, round(reg, 3)


def analyse_islands(V, F, UV=None, max_islands=400):
    """Per-island report: the unit DarkOrbit actually models in.

    For every connected component: size, whether it is a flat card, whether it
    is closed, its mirror symmetry and — the interesting one — its rotational
    order, i.e. how many segments a round part was built with.
    """
    V = np.asarray(V, float).reshape(-1, 3)
    F = np.asarray(F, np.int64).reshape(-1, 3)
    lo, hi = V.min(axis=0), V.max(axis=0)
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    eps = diag * 1e-5
    key = np.round(V / max(eps, 1e-12)).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    Vw = V[first]
    Fw = inv[F]
    ok = (Fw[:, 0] != Fw[:, 1]) & (Fw[:, 1] != Fw[:, 2]) & (Fw[:, 0] != Fw[:, 2])
    Fg = Fw[ok]
    uf = UnionFind(len(Vw))
    for a, b in np.concatenate([Fg[:, [0, 1]], Fg[:, [1, 2]], Fg[:, [2, 0]]]):
        uf.union(int(a), int(b))
    lab = _labels(uf, len(Vw))
    n = int(lab.max() + 1)
    face_lab = lab[Fg[:, 0]]
    reports = []
    order = np.argsort(-np.bincount(face_lab, minlength=n))
    for i in order[:max_islands]:
        fmask = face_lab == i
        if not fmask.any():
            continue
        P = Vw[lab == i]
        Fi = Fg[fmask]
        ilo, ihi = P.min(axis=0), P.max(axis=0)
        idim = ihi - ilo
        idiag = float(np.linalg.norm(idim)) or 1.0
        ctr = P.mean(axis=0)
        cov = np.cov((P - ctr).T)
        ev, evec = np.linalg.eigh(cov)
        flat = bool(ev[-1] > 0 and ev[0] / ev[-1] < 1e-6)
        E = np.sort(np.concatenate([Fi[:, [0, 1]], Fi[:, [1, 2]], Fi[:, [2, 0]]]),
                    axis=1)
        _, ec = np.unique(E, axis=0, return_counts=True)
        tol = idiag * 3e-3
        best = (0, 0.0, "")
        cands = [("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1)),
                 ("pca0", evec[:, 0]), ("pca1", evec[:, 1]), ("pca2", evec[:, 2])]
        for nm, ax in cands:
            k, f = rotational_order(P, ax, ctr, tol)
            if k > best[0]:
                best = (k, f, nm)
        # roundness: sphere fit, and segment slots around the most likely axis
        _c, _r, srms = fit_sphere(P)
        axis_map = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1),
                    "pca0": evec[:, 0], "pca1": evec[:, 1], "pca2": evec[:, 2]}
        # thin axis of a disc / long axis of a tube is the lathe axis candidate
        lathe = evec[:, 0] if ev[0] < ev[-1] * 0.2 else evec[:, 2]
        if best[2]:
            lathe = np.asarray(axis_map[best[2]], float)
        slots, reg = radial_slots(P, lathe, ctr)
        # vertex valence (6 everywhere = geodesic/subdivided; mixed = hand built)
        val = np.bincount(np.concatenate(
            [Fi[:, 0], Fi[:, 1], Fi[:, 2]]).astype(int))
        val = val[val > 0]
        reports.append({
            "island": int(i), "tris": int(fmask.sum()), "verts": int(len(P)),
            "size": [round(float(x), 3) for x in idim],
            "diag": round(idiag, 3),
            "flat_card": flat,
            "closed": bool((ec == 1).sum() == 0),
            "boundary_edges": int((ec == 1).sum()),
            "rot_order": best[0], "rot_frac": round(best[1], 3),
            "rot_axis": best[2],
            "radial_slots": int(slots), "slot_regularity": reg,
            "sphere_fit_rms_rel": round(srms, 4),
            "median_valence": int(np.median(val)) if len(val) else 0,
            "aspect": round(float(max(idim) / max(min(idim), 1e-9)), 2),
            "size_share_of_asset": round(idiag / diag, 3),
        })
    return reports


def _rot(axis, ca, sa):
    x, y, z = axis
    C = 1 - ca
    return np.array([
        [ca + x * x * C, x * y * C - z * sa, x * z * C + y * sa],
        [y * x * C + z * sa, ca + y * y * C, y * z * C - x * sa],
        [z * x * C - y * sa, z * y * C + x * sa, ca + z * z * C]])


# --------------------------------------------------------------------------- #
# loaders so the same audit runs on Astrion assets
# --------------------------------------------------------------------------- #
def load_obj(path):
    V, UV, F = [], [], []
    for line in open(path, "r", encoding="utf-8", errors="replace"):
        if line.startswith("v "):
            V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            UV.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                F.append([idx[0], idx[i], idx[i + 1]])
    return (np.array(V), np.array(F, dtype=np.int64),
            np.array(UV) if len(UV) == len(V) else None, None)


def load_glb(path):
    """Minimal GLB reader: concatenates every primitive of every mesh."""
    import json
    import struct as _s
    raw = open(path, "rb").read()
    assert raw[:4] == b"glTF", "not a GLB"
    off, js, bin_ = 12, None, b""
    while off < len(raw):
        ln, ty = _s.unpack_from("<II", raw, off)
        chunk = raw[off + 8:off + 8 + ln]
        if ty == 0x4E4F534A:
            js = json.loads(chunk)
        elif ty == 0x004E4942:
            bin_ = chunk
        off += 8 + ln + ((4 - ln % 4) % 4 if ln % 4 else 0)
    CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
          5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
    NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def acc(i):
        a = js["accessors"][i]
        code, sz = CT[a["componentType"]]
        n = NC[a["type"]]
        bv = js["bufferViews"][a["bufferView"]]
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", sz * n)
        out = np.empty((a["count"], n))
        for k in range(a["count"]):
            out[k] = _s.unpack_from("<" + code * n, bin_, base + k * stride)
        return out

    Vs, Fs, Us, Ns, base = [], [], [], [], 0
    any_normal = False
    for m in js.get("meshes", []):
        for p in m["primitives"]:
            if p.get("mode", 4) != 4:
                continue
            attrs = p["attributes"]
            pos = acc(attrs["POSITION"])
            idx = acc(p["indices"]).astype(np.int64).ravel() if "indices" in p \
                else np.arange(len(pos))
            uv = acc(attrs["TEXCOORD_0"]) if "TEXCOORD_0" in attrs else None
            nrm = acc(attrs["NORMAL"]) if "NORMAL" in attrs else None
            any_normal = any_normal or nrm is not None
            Vs.append(pos)
            Fs.append(idx.reshape(-1, 3) + base)
            Us.append(uv if uv is not None else np.zeros((len(pos), 2)))
            Ns.append(nrm if nrm is not None else np.zeros((len(pos), 3)))
            base += len(pos)
    V = np.concatenate(Vs); F = np.concatenate(Fs); U = np.concatenate(Us)
    N = np.concatenate(Ns) if any_normal else None
    return V, F, U, N


if __name__ == "__main__":
    import json
    import sys
    for f in sys.argv[1:]:
        if f.lower().endswith(".glb"):
            V, F, U, N = load_glb(f)
        else:
            V, F, U, N = load_obj(f)
        r = analyse(V, F, U, N, name=f)
        r.pop("_rot_table", None)
        print(json.dumps(r, indent=2))
