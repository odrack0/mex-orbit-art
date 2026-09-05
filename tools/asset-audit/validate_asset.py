#!/usr/bin/env python3
"""validate_asset - comprueba un asset de Astrion contra el
ASTRION LOW-POLY MODELING STANDARD.

Lee un GLB u OBJ, calcula las metricas con mesh_metrics y aplica los umbrales
de la seccion 10 del estandar. Devuelve codigo 1 si hay algun ERROR.

    py validate_asset.py modelo.glb --type=npc_normal
    py validate_asset.py modelo.glb --type=player_ship --organic --json

Tipos: prop, prop_grande, dron, pet, npc_normal, npc_complejo, elite, boss,
       uber, player_ship, estructura, portal, fx

La densidad en pantalla usa la camara documentada del proyecto (FOV 30,
elevacion 45, azimut 25, d=1740) a 1440p y zoom 1: 1,5443 px por unidad.
Si el asset no esta en unidades de mundo, la comprobacion de escala falla
primero y la de densidad se marca como no evaluable.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

from mesh_metrics import (GAME_CAM_AZIMUTH_DEG, GAME_CAM_ELEVATION_DEG,
                          analyse, analyse_islands, camera_dir, load_glb,
                          load_obj, projected_px_area)

# Camara del proyecto a 1440p, zoom 1.
PX_PER_UNIT_1440 = 1440.0 / (2 * 1740 * math.tan(math.radians(15)))

TRI_BUDGET = {
    "prop": (200, 800), "prop_grande": (800, 2500), "dron": (400, 1200),
    "pet": (2000, 4000), "npc_normal": (2000, 4000),
    "npc_complejo": (4000, 7000), "elite": (6000, 10000),
    "boss": (9000, 16000), "uber": (14000, 25000),
    "player_ship": (10000, 20000), "estructura": (8000, 20000),
    "portal": (4000, 9000), "fx": (2, 24),
}

PIECES = {
    "prop": (1, 4), "prop_grande": (1, 8), "dron": (1, 6), "pet": (4, 12),
    "npc_normal": (4, 12), "npc_complejo": (8, 20), "elite": (8, 20),
    "boss": (12, 30), "uber": (12, 30), "player_ship": (8, 20),
    "estructura": (15, 40), "portal": (8, 24), "fx": (1, 6),
}

FLATNESS = {
    "player_ship": (0.35, 0.55), "npc_normal": (0.35, 0.75),
    "npc_complejo": (0.35, 0.75), "elite": (0.35, 0.75),
    "boss": (0.40, 0.80), "uber": (0.40, 0.80),
    "dron": (0.40, 0.70), "pet": (0.40, 0.70),
    "estructura": (0.60, 1.15), "portal": (0.85, 1.15),
}

# Techo de densidad en pantalla (estandar §4.2). Solo se aplica por encima de
# DENSITY_FLOOR_TRIS: por debajo manda el suelo de forma, no la cobertura.
DENSITY_WARN = 800.0
DENSITY_HARD = 2000.0
DENSITY_FLOOR_TRIS = 1000
SCALE_RANGE = (20.0, 400.0)


class Report:
    def __init__(self):
        self.rows = []

    def add(self, level, check, value, expected, note=""):
        self.rows.append({"level": level, "check": check, "value": value,
                          "expected": expected, "note": note})

    def ok(self, check, value, expected, note=""):
        self.add("OK", check, value, expected, note)

    def warn(self, check, value, expected, note=""):
        self.add("AVISO", check, value, expected, note)

    def err(self, check, value, expected, note=""):
        self.add("ERROR", check, value, expected, note)

    def band(self, check, value, lo, hi, hard=False):
        if value is None:
            self.add("N/E", check, None, f"{lo}..{hi}", "no evaluable")
        elif lo <= value <= hi:
            self.ok(check, value, f"{lo}..{hi}")
        elif hard:
            self.err(check, value, f"{lo}..{hi}")
        else:
            self.warn(check, value, f"{lo}..{hi}")

    @property
    def errors(self):
        return sum(1 for r in self.rows if r["level"] == "ERROR")

    @property
    def warnings(self):
        return sum(1 for r in self.rows if r["level"] == "AVISO")


def screen_px_area(V, F, px_per_unit):
    """Area proyectada del asset en px^2 desde la camara de juego (union, no
    suma de triangulos: se rasteriza la mascara)."""
    from mesh_metrics import visible_triangle_area
    d = camera_dir(GAME_CAM_ELEVATION_DEG, GAME_CAM_AZIMUTH_DEG)
    size = float(np.linalg.norm(V.max(0) - V.min(0)))
    res = max(32, min(1024, int(round(size * px_per_unit))))
    _c, ibuf, _s = visible_triangle_area(V, F, d, res=res)
    return float((ibuf >= 0).sum()), res


def validate(path, kind, organic=False, fx=False, world_scale=1.0):
    rep = Report()
    if path.lower().endswith(".glb") or path.lower().endswith(".gltf"):
        V, F, U, N = load_glb(path)
    else:
        V, F, U, N = load_obj(path)
    # Los GLB fuente vienen normalizados. El cliente los escala para que su
    # extension mayor valga `screen_size` unidades de mundo (entity_node.gd:
    # _body_scale = screen_size / extent_3d). --screen-size reproduce eso;
    # --world-scale es el multiplicador crudo para casos sueltos.
    if world_scale != 1.0:
        V = V * float(world_scale)
    m = analyse(V, F, U, N, name=os.path.basename(path), heavy=True,
                px_per_unit=PX_PER_UNIT_1440)
    m.pop("_rot_table", None)
    pieces = analyse_islands(V, F)

    # ---- escala ---------------------------------------------------------- #
    diag = m["bbox_diag"]
    rep.band("escala: diagonal de la caja (unidades)", round(diag, 1),
             *SCALE_RANGE, hard=True)
    ctr = (V.max(0) + V.min(0)) / 2
    off = float(np.linalg.norm(ctr)) / max(diag, 1e-9)
    if off <= 0.05:
        rep.ok("origen centrado (fraccion de la diagonal)", round(off, 3), "<= 0.05")
    else:
        rep.err("origen centrado (fraccion de la diagonal)", round(off, 3), "<= 0.05")

    scale_ok = SCALE_RANGE[0] <= diag <= SCALE_RANGE[1]

    # ---- presupuesto ----------------------------------------------------- #
    lo, hi = TRI_BUDGET.get(kind, (0, 10 ** 9))
    rep.band(f"triangulos ({kind})", m["tris"], lo, hi)

    if scale_ok:
        px_area, res = screen_px_area(V, F, PX_PER_UNIT_1440)
        dens = m["tris"] / max(px_area / 1000.0, 1e-9)
        rep.add("OK", "tamano en pantalla (px de alto, 1440p zoom 1)",
                round(m["bbox_diag"] * PX_PER_UNIT_1440, 1), "informativo")
        exp = f"<= {DENSITY_WARN:.0f} (error > {DENSITY_HARD:.0f})"
        if m["tris"] < DENSITY_FLOOR_TRIS:
            rep.add("N/E", "densidad (tris por 1.000 px^2)", round(dens, 1), exp,
                    f"no aplica por debajo de {DENSITY_FLOOR_TRIS} tris")
        elif dens > DENSITY_HARD:
            rep.err("densidad (tris por 1.000 px^2)", round(dens, 1), exp,
                    "el asset pesa como un boss y ocupa como un prop")
        elif dens > DENSITY_WARN:
            rep.warn("densidad (tris por 1.000 px^2)", round(dens, 1), exp)
        else:
            rep.ok("densidad (tris por 1.000 px^2)", round(dens, 1), exp)
    else:
        rep.add("N/E", "densidad (tris por 1.000 px^2)", None, "-",
                "la escala esta fuera de rango")

    # ---- higiene de malla (todo error) ----------------------------------- #
    for key, label in (("duplicate_faces", "caras duplicadas"),
                       ("degenerate_tris", "triangulos degenerados"),
                       ("nonmanifold_edges", "aristas no-manifold")):
        v = m.get(key, 0)
        (rep.ok if v == 0 else rep.err)(label, v, "0")

    unused = len(V) - len(np.unique(F))
    (rep.ok if unused == 0 else rep.err)("vertices sueltos", unused, "0")

    zero = sum(1 for p in pieces if p["flat_card"])
    if fx:
        rep.ok("piezas de grosor cero", zero, "permitido en FX")
    else:
        (rep.ok if zero == 0 else rep.err)("piezas de grosor cero", zero, "0")

    thin = [p for p in pieces
            if not p["flat_card"] and p["diag"] > 0
            and min(p["size"]) < max(0.3, 0.008 * max(p["size"]))]
    (rep.ok if not thin else rep.warn)(
        "piezas mas finas que el minimo (0,8 % / 0,3 u)", len(thin), "0",
        ", ".join(f"isla {p['island']}" for p in thin[:5]))

    # ---- geometria enterrada --------------------------------------------- #
    interior = m.get("interior_tri_ratio")
    if interior is None:
        rep.add("N/E", "triangulos nunca visibles", None, "<= 5 %")
    elif interior <= 0.05:
        rep.ok("triangulos nunca visibles", f"{interior:.1%}", "<= 5 %")
    else:
        rep.err("triangulos nunca visibles", f"{interior:.1%}", "<= 5 %",
                "geometria enterrada; solo se permite si una animacion la revela")

    # ---- estructura ------------------------------------------------------ #
    plo, phi = PIECES.get(kind, (1, 40))
    rep.band("piezas visibles", m["islands"], plo, phi)
    rep.band("cuota de triangulos de la pieza mayor",
             m["largest_island_tri_share"], 0.40, 1.0)

    if kind in FLATNESS:
        bx, by, bz = m["bbox_x"], m["bbox_y"], m["bbox_z"]
        flat = by / max(bx, bz, 1e-9)
        rep.band("aplanamiento alto/max(ancho,largo)", round(flat, 3),
                 *FLATNESS[kind])

    # ---- topologia y UV -------------------------------------------------- #
    rep.band("ratio de quads", m["quad_tri_ratio"], 0.60, 1.0)
    if m.get("has_uv"):
        rep.band("ocupacion de UV", m.get("uv_coverage"), 0.75, 1.0)
    else:
        rep.err("UV presentes", False, "True")
    (rep.ok if m.get("has_normals_stream") else rep.err)(
        "normales explicitas exportadas", m.get("has_normals_stream"), "True")

    thr = 0.60 if organic else 0.95
    rep.band("simetria en X", m.get("best_mirror_frac"), thr, 1.0)

    # ---- primitivas redondas --------------------------------------------- #
    bad_round = [p for p in pieces
                 if p["radial_slots"] >= 3 and p["slot_regularity"] < 0.85
                 and p["rot_order"] == 0 and p["tris"] >= 24]
    (rep.ok if not bad_round else rep.warn)(
        "piezas redondas irregulares (deberian ser primitivas exactas)",
        len(bad_round), "0",
        ", ".join(f"isla {p['island']} ({p['radial_slots']} pos.)"
                  for p in bad_round[:5]))

    over = [p for p in pieces if p["rot_order"] > 24]
    (rep.ok if not over else rep.warn)(
        "piezas torneadas con mas de 24 segmentos", len(over), "0",
        ", ".join(f"isla {p['island']} ({p['rot_order']})" for p in over[:5]))

    return rep, m, pieces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--type", default="npc_normal", choices=sorted(TRI_BUDGET))
    ap.add_argument("--organic", action="store_true",
                    help="asset asimetrico declarado en el brief")
    ap.add_argument("--screen-size", type=float, default=None,
                    help="el `screen_size` del JSON de la especie: escala el "
                         "modelo para que su extension mayor valga esas "
                         "unidades de mundo, igual que hace el cliente")
    ap.add_argument("--world-scale", type=float, default=1.0,
                    help="multiplicador crudo, alternativa a --screen-size")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ws = a.world_scale
    if a.screen_size:
        if a.model.lower().endswith((".glb", ".gltf")):
            V0, _F, _U, _N = load_glb(a.model)
        else:
            V0, _F, _U, _N = load_obj(a.model)
        ext = float((V0.max(0) - V0.min(0)).max())
        ws = a.screen_size / max(ext, 1e-9)

    rep, m, pieces = validate(a.model, a.type, a.organic, a.type == "fx", ws)

    if a.json:
        print(json.dumps({"model": a.model, "type": a.type,
                          "checks": rep.rows, "metrics": m}, indent=1,
                         default=str))
    else:
        icon = {"OK": "  ok  ", "AVISO": " AVISO", "ERROR": " ERROR", "N/E": "  n/e "}
        print(f"\n{os.path.basename(a.model)}  ({a.type})  "
              f"{m['tris']} tris, {m['islands']} piezas\n")
        for r in rep.rows:
            print(f"[{icon[r['level']]}] {r['check']:52} "
                  f"{str(r['value']):>12}   esperado {r['expected']}"
                  + (f"   {r['note']}" if r["note"] else ""))
        print(f"\n{rep.errors} errores, {rep.warnings} avisos")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
