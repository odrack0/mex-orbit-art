# -*- coding: utf-8 -*-
"""Mide los anclajes de un render para su JSON de definicion.

Devuelve coordenadas EN EL ESPACIO DE LA TEXTURA con el origen en su centro,
que es lo que consume data/ships/<nave>.json.

Dos modos, porque no todas las naves se miden igual:

  emisivo  Encuentra las toberas por su color encendido (cian por defecto).
           Sirve cuando el render tiene los motores brillando.

  geom     Encuentra los salientes por la SILUETA: recorre filas contando
           tramos opacos separados. Sirve cuando las toberas son metal apagado
           —la capsula Phoenix no tiene un solo pixel encendido— y ademas
           localiza los canones laterales, que el modo emisivo nunca vio.

Uso:  py -3 tools/find-anchors.py <export.png> [emisivo|geom] [canal|-] [umbral]
Ej.:  py -3 tools/find-anchors.py exports/phoenix.png geom
      py -3 tools/find-anchors.py exports/vex.png emisivo r 40
"""
import sys

import numpy as np
from PIL import Image

ruta = sys.argv[1]
modo = sys.argv[2] if len(sys.argv) > 2 else 'emisivo'

im = Image.open(ruta).convert('RGBA')
a = np.array(im)
alfa = a[:, :, 3] > 40
H, W = alfa.shape
cx, cy = W / 2.0, H / 2.0
ys, xs = np.nonzero(alfa)
print('bbox de la pieza: x %d-%d  y %d-%d  (textura %dx%d)'
      % (xs.min(), xs.max(), ys.min(), ys.max(), W, H))


def tramos(y, minimo=3):
    """Tramos opacos de una fila: (inicio, fin, centro)."""
    fila = alfa[y]
    out, ini = [], None
    for x in range(W):
        if fila[x] and ini is None:
            ini = x
        elif not fila[x] and ini is not None:
            if x - ini >= minimo:
                out.append((ini, x - 1, (ini + x - 1) // 2))
            ini = None
    if ini is not None and W - ini >= minimo:
        out.append((ini, W - 1, (ini + W - 1) // 2))
    return out


if modo == 'geom':
    # --- TOBERAS: la fila mas baja donde los salientes de popa siguen separados.
    # Mas abajo las campanas se abren y se solapan; mas arriba aun no han salido
    # del casco. Esa franja da los centros estables.
    mejor = None
    for y in range(int(H * 0.85), int(H * 0.99)):
        t = tramos(y)
        if len(t) >= 2 and (mejor is None or len(t) > len(mejor[1])):
            mejor = (y, t)
    if mejor:
        y, t = mejor
        # la boca esta en el extremo de popa: se baja hasta donde aun hay pieza
        boca = max(yy for yy in range(y, H) if alfa[yy].any())
        print('\n"engines": [   // %d toberas, fila de medida y=%d, boca y=%d' % (len(t), y, boca))
        for i, (_, _, c) in enumerate(t):
            coma = ',' if i < len(t) - 1 else ''
            print('  { "x": %d, "y": %d, "scale": 1.0 }%s' % (c - cx, boca - 2 - cy, coma))
        print(']')

    # --- CAÑONES: la fila mas alta donde aparecen tramos separados del casco a
    # izquierda Y derecha, y ADEMAS bien afuera.
    #
    # El filtro de "bien afuera" no es cosmetico: sin el, la primera fila con
    # tres tramos era el domo de la capsula con sus dos asideros curvos, a un
    # 64% del semiancho. Los tubos de verdad estan al 91%. Se exige el 80%.
    semiancho = (xs.max() - xs.min()) / 2.0
    for y in range(int(H * 0.15), int(H * 0.60)):
        t = tramos(y)
        if len(t) < 3:
            continue
        izq, der = t[0], t[-1]
        if min(abs(izq[2] - cx), abs(der[2] - cx)) < semiancho * 0.80:
            continue
        print('\n"cannons": [   // boca de cada tubo, fila y=%d (%.0f%% del semiancho)'
              % (y, 100.0 * abs(izq[2] - cx) / semiancho))
        print('  { "x": %d, "y": %d },' % (izq[2] - cx, y - cy))
        print('  { "x": %d, "y": %d }' % (der[2] - cx, y - cy))
        print(']')
        break
    else:
        print('\nsin canones laterales claros: la nave puede no tenerlos')
    raise SystemExit(0)

# ---- modo emisivo (el original) ----
canal = sys.argv[3] if len(sys.argv) > 3 else 'c'
umbral = int(sys.argv[4]) if len(sys.argv) > 4 else 40
r, g, b = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
if canal == 'c':
    exceso = np.minimum(g, b) - r
elif canal == 'r':
    exceso = r - np.maximum(g, b)
else:
    exceso = np.minimum(r, b) - g
emisivo = alfa & (exceso > umbral)
ye, xe = np.nonzero(emisivo)
if len(ye) == 0:
    print('sin pixeles emisivos con ese canal/umbral — prueba el modo geom')
    raise SystemExit(1)
popa = ye > H * 0.72
if popa.sum() == 0:
    print('sin emisivos en la popa: revisa el umbral')
    raise SystemExit(1)
xb, yb = xe[popa], ye[popa]
izq = xb < W // 2
print('anclajes para el JSON (espacio de textura, origen al centro):')
if izq.sum():
    print('  { "x": %d, "y": %d, "scale": 1.0 },' % (xb[izq].mean() - cx, yb[izq].mean() - cy))
if (~izq).sum():
    print('  { "x": %d, "y": %d, "scale": 1.0 }' % (xb[~izq].mean() - cx, yb[~izq].mean() - cy))
