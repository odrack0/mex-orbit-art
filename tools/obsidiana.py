# -*- coding: utf-8 -*-
"""Pasada de coherencia "Obsidiana" — version RASTER (dictamen PNG, 2026-08-25).

No redibuja la nave: el render pone la forma y la LUZ (luminancia pixel a pixel,
detalle integro) y esta pasada sustituye el MATERIAL para que todo el catalogo
comparta familia: casco obsidiana -> grafito, especulares rematados en oro, y el
decorado saturado (franjas, emisivos) unificado a turquesa.

Uso:  py -3 tools/obsidiana.py <entrada-cut.png> <salida.png> [fuerza 0..1] [sat_decorado]
Ej.:  py -3 tools/obsidiana.py source/renders/phoenix-cut.png exports/phoenix-obsidiana.png 1.0 0.25
"""
import sys

import numpy as np
from PIL import Image

ENTRADA, SALIDA = sys.argv[1], sys.argv[2]
FUERZA = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
SAT_DECOR = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25

# obsidiana -> grafito -> oro especular (la paleta del diseno original)
METAL = [
    (0.00, (0x0c, 0x0f, 0x14)),
    (0.25, (0x1b, 0x20, 0x29)),
    (0.45, (0x2c, 0x33, 0x3f)),
    (0.62, (0x41, 0x4a, 0x58)),
    (0.75, (0x5c, 0x66, 0x75)),
    (0.85, (0x7d, 0x88, 0x96)),
    (0.91, (0xa3, 0x94, 0x6a)),
    (0.96, (0xd8, 0xb9, 0x72)),
    (1.00, (0xf9, 0xed, 0xd4)),
]
# turquesa de incrustacion
INLAY = [
    (0.00, (0x04, 0x2a, 0x30)),
    (0.30, (0x0a, 0x5f, 0x6b)),
    (0.55, (0x14, 0x9b, 0xa6)),
    (0.78, (0x3d, 0xd2, 0xd6)),
    (1.00, (0xc6, 0xf7, 0xf7)),
]


def rampa_lut(stops):
    """LUT de 256 entradas interpolando la rampa."""
    lut = np.zeros((256, 3), dtype=np.float32)
    for i in range(256):
        t = i / 255.0
        for k in range(len(stops) - 1):
            a, ca = stops[k]
            b, cb = stops[k + 1]
            if a <= t <= b:
                f = 0.0 if b == a else (t - a) / (b - a)
                lut[i] = [ca[j] + (cb[j] - ca[j]) * f for j in range(3)]
                break
        else:
            lut[i] = stops[-1][1]
    return lut


img = Image.open(ENTRADA).convert('RGBA')
arr = np.array(img).astype(np.float32)
rgb, alfa = arr[:, :, :3], arr[:, :, 3]
nave = alfa > 40

lum = rgb[:, :, 0] * .299 + rgb[:, :, 1] * .587 + rgb[:, :, 2] * .114
# normalizacion por percentiles de la nave: la rampa usa TODO su rango dinamico
lo, hi = np.percentile(lum[nave], 1.0), np.percentile(lum[nave], 99.5)
t = np.clip((lum - lo) / max(1e-6, hi - lo), 0, 1)

mx = rgb.max(axis=2)
mn = rgb.min(axis=2)
sat = np.where(mx > 1, (mx - mn) / np.maximum(mx, 1), 0.0)
decorado = nave & (sat > SAT_DECOR) & (mx > 45)
metal = nave & ~decorado

idx = (t * 255).astype(np.uint8)
lut_metal = rampa_lut(METAL)
lut_inlay = rampa_lut(INLAY)

salida = rgb.copy()
salida[metal] = lut_metal[idx[metal]]
salida[decorado] = lut_inlay[idx[decorado]]

# fuerza < 1 mezcla con el original (dial de calibracion del dictamen)
if FUERZA < 1.0:
    salida = rgb * (1 - FUERZA) + salida * FUERZA

resultado = np.dstack([np.clip(salida, 0, 255), alfa]).astype(np.uint8)
Image.fromarray(resultado, 'RGBA').save(SALIDA, optimize=True)
print(f'{SALIDA}  metal={int(metal.sum())}px  decorado={int(decorado.sum())}px  fuerza={FUERZA}')
