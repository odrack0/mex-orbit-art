# -*- coding: utf-8 -*-
"""Donde SE VE girar un anillo: perfil de asimetria angular por radio.

Rotar un anillo perfectamente liso mapea pixeles identicos sobre si mismos y no
se ve absolutamente nada. Este script recorre circulos concentricos y mide
cuanto varia el contenido a lo largo de cada uno: las bandas con variacion alta
son las unicas donde el giro del shader `rings` produce lectura.

Se aprendio a la mala con el Gravon: su banda movil estaba cortada en r 0.24,
justo ANTES de donde empieza su detalle asimetrico, y el efecto era invisible.

Uso:  py -3 tools/ring-bands.py exports/gravon.png
"""
import math
import statistics
import sys

from PIL import Image

ruta = sys.argv[1]
im = Image.open(ruta).convert('RGBA')
px = im.load()
N = im.size[0]
c = N / 2.0

print('radio (UV)  variacion angular   (>22 = rotar ahi se ve)')
for i in range(2, 16):
    r = i / 32.0
    vals = []
    for k in range(360):
        a = k * math.pi / 180.0
        x, y = int(c + math.cos(a) * r * N), int(c + math.sin(a) * r * N)
        if 0 <= x < N and 0 <= y < N:
            p = px[x, y]
            vals.append((p[0] * 0.3 + p[1] * 0.6 + p[2] * 0.1) * (p[3] / 255.0))
    sd = statistics.pstdev(vals) if vals else 0.0
    print('  %.3f      %5.1f  %s%s' % (r, sd, '#' * int(sd / 2),
                                       '  <-- ASIMETRICO' if sd > 22 else ''))
