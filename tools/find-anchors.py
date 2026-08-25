# -*- coding: utf-8 -*-
"""Mide los anclajes de un render para su JSON de definicion.

Encuentra las toberas por su color emisivo (cian por defecto) en el tercio
inferior de la nave y devuelve sus coordenadas EN EL ESPACIO DE LA TEXTURA
(origen en el centro), que es lo que consume data/ships/<nave>.json.

Uso:  py -3 tools/find-anchors.py <export.png> [canal c|r|m] [umbral]
Ej.:  py -3 tools/find-anchors.py exports/phoenix.png c 40
"""
import sys

import numpy as np
from PIL import Image

ruta = sys.argv[1]
canal = sys.argv[2] if len(sys.argv) > 2 else 'c'
umbral = int(sys.argv[3]) if len(sys.argv) > 3 else 40

im = Image.open(ruta).convert('RGBA')
a = np.array(im)
alfa = a[:, :, 3] > 40
r, g, b = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)

if canal == 'c':
    exceso = np.minimum(g, b) - r
elif canal == 'r':
    exceso = r - np.maximum(g, b)
else:
    exceso = np.minimum(r, b) - g

emisivo = alfa & (exceso > umbral)
ys, xs = np.nonzero(alfa)
print(f'bbox de la pieza: x {xs.min()}-{xs.max()}  y {ys.min()}-{ys.max()}  (textura {im.width}x{im.height})')

ye, xe = np.nonzero(emisivo)
if len(ye) == 0:
    print('sin pixeles emisivos con ese canal/umbral')
    raise SystemExit(1)

popa = ye > im.height * 0.72          # el tercio de popa
if popa.sum() == 0:
    print('sin emisivos en la popa: revisa el umbral')
    raise SystemExit(1)

xb, yb = xe[popa], ye[popa]
izq = xb < im.width // 2
cx, cy = im.width / 2, im.height / 2
print('anclajes para el JSON (espacio de textura, origen al centro):')
if izq.sum():
    print(f'  {{ "x": {int(xb[izq].mean() - cx)}, "y": {int(yb[izq].mean() - cy)}, "scale": 1.0 }},')
if (~izq).sum():
    print(f'  {{ "x": {int(xb[~izq].mean() - cx)}, "y": {int(yb[~izq].mean() - cy)}, "scale": 1.0 }}')
