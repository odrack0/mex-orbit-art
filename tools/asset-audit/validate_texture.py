#!/usr/bin/env python3
"""validate_texture - comprueba el set PBR de un GLB contra el brief de
texturas (`mex-orbit-art/prompts/texturas.md`, seccion 3).

Las bandas salen de la luz real del cliente
(`mex-orbit-client/data/config/lighting.json`): un sol blanco a energia 1,0 con
specular 0,7, ambiente rosado a 0,2, sin sombras, cielo de reflexion casi negro
y `metallic_scale` 0,6 / `roughness_scale` 0,9.

    py validate_texture.py modelo.glb [--emissive-channel=c] [--json]

Canales de emision: r g b (primarios) o c m y (secundarios), la misma
heuristica que normalize-model.py y extract-emissive.py.
"""
from __future__ import annotations

import argparse
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

# Bandas del brief (luminancia y valores en sRGB, tal como los ve el generador).
BASE_P50 = (0.28, 0.45)
BASE_P95_MAX = 0.65
BASE_P05_MIN = 0.08
ROUGH_P50 = (0.45, 0.70)
ROUGH_MIN = 0.30
METAL_BODY_MAX = 0.25
METAL_HIGH_AREA_MAX = 0.20
EMISSIVE_AREA_MIN = 0.03
EMISSIVE_P99_MIN = 0.5


def read_glb(path):
    raw = open(path, "rb").read()
    if raw[:4] != b"glTF":
        raise ValueError("no es un GLB")
    off, js, bin_ = 12, None, b""
    while off < len(raw):
        ln, ty = struct.unpack_from("<II", raw, off)
        chunk = raw[off + 8:off + 8 + ln]
        if ty == 0x4E4F534A:
            js = json.loads(chunk)
        elif ty == 0x004E4942:
            bin_ = chunk
        off += 8 + ln + ((4 - ln % 4) % 4 if ln % 4 else 0)
    return js, bin_


def images_by_role(js, bin_):
    role = {}
    for m in js.get("materials", []):
        p = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in p:
            role.setdefault("base", p["baseColorTexture"]["index"])
        if "metallicRoughnessTexture" in p:
            role.setdefault("orm", p["metallicRoughnessTexture"]["index"])
        if "normalTexture" in m:
            role.setdefault("normal", m["normalTexture"]["index"])
        if "emissiveTexture" in m:
            role.setdefault("emissive", m["emissiveTexture"]["index"])
        if "occlusionTexture" in m:
            role.setdefault("ao", m["occlusionTexture"]["index"])

    out = {}
    for k, ti in role.items():
        tex = js["textures"][ti]
        img = js["images"][tex["source"]]
        if "bufferView" not in img:
            continue
        bv = js["bufferViews"][img["bufferView"]]
        o = bv.get("byteOffset", 0)
        out[k] = Image.open(io.BytesIO(bin_[o:o + bv["byteLength"]]))
    return out


def arr(im):
    return np.asarray(im.convert("RGB"), np.float32) / 255.0


def luminance(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def channel_mask(a, ch):
    """Mascara del canal dominante — misma heuristica que normalize-model.py:
    primarios contra el mayor de los otros dos; secundarios, el menor de sus
    dos canales contra el que falta."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    if ch == "r":
        return r - np.maximum(g, b)
    if ch == "g":
        return g - np.maximum(r, b)
    if ch == "b":
        return b - np.maximum(r, g)
    if ch == "c":
        return np.minimum(g, b) - r
    if ch == "m":
        return np.minimum(r, b) - g
    if ch == "y":
        return np.minimum(r, g) - b
    raise ValueError(f"canal desconocido: {ch}")


def best_channel(a):
    best, name = None, ""
    for ch in "rgbcmy":
        m = np.clip(channel_mask(a, ch), 0, 1)
        score = (m > EMISSIVE_P99_MIN).mean()
        if best is None or score > best:
            best, name = score, ch
    return name, best


class Rep:
    def __init__(self):
        self.rows = []

    def add(self, lvl, check, val, exp, note=""):
        self.rows.append({"level": lvl, "check": check, "value": val,
                          "expected": exp, "note": note})

    def band(self, check, v, lo, hi, hard=False):
        if v is None:
            self.add("N/E", check, None, f"{lo}..{hi}")
        elif lo <= v <= hi:
            self.add("OK", check, round(v, 3), f"{lo}..{hi}")
        else:
            self.add("ERROR" if hard else "AVISO", check, round(v, 3),
                     f"{lo}..{hi}")

    @property
    def errors(self):
        return sum(1 for r in self.rows if r["level"] == "ERROR")

    @property
    def warnings(self):
        return sum(1 for r in self.rows if r["level"] == "AVISO")


def validate(path, emissive_channel=None):
    js, bin_ = read_glb(path)
    imgs = images_by_role(js, bin_)
    rep = Rep()

    present = sorted(imgs)
    rep.add("OK" if "base" in imgs else "ERROR", "mapas presentes",
            "+".join(present) or "ninguno", "base+orm+normal(+emissive)")
    for k, lvl in (("orm", "ERROR"), ("normal", "AVISO")):
        if k not in imgs:
            rep.add(lvl, f"mapa '{k}'", "falta",
                    "presente",
                    "sin mapa de rugosidad el cliente aplica 0,35 plano a todo"
                    if k == "orm" else "el relieve medio se pierde")
    if "ao" in imgs:
        rep.add("AVISO", "mapa 'ao'", "presente", "no entregar",
                "el cliente no cablea oclusion; es luz horneada")

    if "base" not in imgs:
        return rep, {}

    a = arr(imgs["base"])
    lum = luminance(a)
    stats = {"base_px": imgs["base"].size[0]}
    p05, p50, p95 = (float(np.percentile(lum, q)) for q in (5, 50, 95))
    stats.update(base_p05=p05, base_p50=p50, base_p95=p95)
    rep.band("base color: luminancia p50", p50, *BASE_P50)
    rep.band("base color: luminancia p95 (brillos horneados)", p95, 0.0,
             BASE_P95_MAX)
    rep.band("base color: luminancia p05 (negros aplastados)", p05,
             BASE_P05_MIN, 1.0)
    rng = p95 - p05
    rep.band("base color: rango p95-p05", rng, 0.0, 0.55)

    if "orm" in imgs:
        o = arr(imgs["orm"])
        rough, metal = o[..., 1], o[..., 2]
        rp50 = float(np.percentile(rough, 50))
        stats.update(rough_p50=rp50, rough_p05=float(np.percentile(rough, 5)),
                     metal_p50=float(np.percentile(metal, 50)),
                     metal_area_high=float((metal > 0.5).mean()))
        rep.band("rugosidad: p50", rp50, *ROUGH_P50)
        rep.band("rugosidad: p05 (espejo negro por debajo)",
                 stats["rough_p05"], ROUGH_MIN, 1.0)
        rep.band("metalico: p50 del cuerpo", stats["metal_p50"], 0.0,
                 METAL_BODY_MAX)
        rep.band("metalico: area por encima de 0,5", stats["metal_area_high"],
                 0.0, METAL_HIGH_AREA_MAX)
        spread = float(np.percentile(rough, 90) - np.percentile(rough, 10))
        stats["rough_spread"] = spread
        rep.band("rugosidad: contraste entre materiales (p90-p10)", spread,
                 0.10, 1.0)

    # Emision. Un modelo ya pasado por normalize-model.py trae su propio mapa
    # emisivo horneado: entonces manda ese, y lo derivable del base color pasa
    # a ser informativo. Un set recien salido del generador no lo trae, y ahi
    # el canal dominante del base color es lo unico que hay que cazar.
    baked_ok = False
    if "emissive" in imgs:
        e = arr(imgs["emissive"])
        area = float((luminance(e) > EMISSIVE_P99_MIN).mean())
        stats["emissive_area"] = area
        baked_ok = area >= EMISSIVE_AREA_MIN
        rep.band("emisivo horneado: area por encima de 0,5", area,
                 EMISSIVE_AREA_MIN, 1.0)

    ch = emissive_channel or best_channel(a)[0]
    m = np.clip(channel_mask(a, ch), 0, 1)
    area = float((m > EMISSIVE_P99_MIN).mean())
    p99 = float(np.percentile(m, 99))
    ok = area >= EMISSIVE_AREA_MIN and p99 > EMISSIVE_P99_MIN
    stats.update(emissive_channel=ch, emissive_derivable_area=area,
                 emissive_p99=p99)
    label = f"emision derivable del base color (canal '{ch}')"
    if ok:
        rep.add("OK", label, f"{area:.1%}",
                f">= {EMISSIVE_AREA_MIN:.0%} y p99 > 0,5")
    elif baked_ok:
        rep.add("N/E", label, f"{area:.1%} (p99 {p99:.2f})",
                f">= {EMISSIVE_AREA_MIN:.0%} y p99 > 0,5",
                "no aplica: el modelo ya trae su emisivo horneado")
    else:
        rep.add("ERROR", label, f"{area:.1%} (p99 {p99:.2f})",
                f">= {EMISSIVE_AREA_MIN:.0%} y p99 > 0,5",
                "las luces estan pintadas como degradado palido, no como "
                "parche plano saturado — no hay canal dominante que extraer")
    return rep, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--emissive-channel", default=None, choices=list("rgbcmy"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rep, stats = validate(a.model, a.emissive_channel)
    if a.json:
        print(json.dumps({"model": a.model, "checks": rep.rows,
                          "stats": stats}, indent=1, default=str))
    else:
        icon = {"OK": "  ok  ", "AVISO": " AVISO", "ERROR": " ERROR",
                "N/E": "  n/e "}
        import os
        print(f"\n{os.path.basename(a.model)}\n")
        for r in rep.rows:
            print(f"[{icon[r['level']]}] {r['check']:48} "
                  f"{str(r['value']):>14}   esperado {r['expected']}"
                  + (f"\n{'':11}{r['note']}" if r["note"] else ""))
        print(f"\n{rep.errors} errores, {rep.warnings} avisos")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
