# -*- coding: utf-8 -*-
"""Quita el fondo verde de un render fijo. El recorte vive en `croma.py`.

Este script tenia su propia copia del criterio, y se quedo atras: mantenia el
despill viejo (quitar el 92% del verde sobrante y SUMAR un 30% a rojo y azul,
que sobre croma puro deja un teal) y el alfa de mascara binaria con desenfoque
encima. El del atlas se rehizo por el contorno de la estacion y este no, porque
eran dos copias. Ahora los dos llaman a lo mismo.

  py -3 tools/chroma-key.py <entrada> <salida.png> [umbral]

Los argumentos LMIN y HOLE_MAX del script viejo ya no existen: el alfa es
continuo, asi que no hay luminancia minima que ajustar, y un hueco cerrado se
decide por si es VERDE, no por su tamanio.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from croma import recortar    # noqa: E402  (tras ajustar sys.path)

SRC, OUT = sys.argv[1], sys.argv[2]
T = float(sys.argv[3]) if len(sys.argv) > 3 else 22.0
if len(sys.argv) > 4:
    print('AVISO: LMIN y HOLE_MAX ya no se usan; ver la cabecera del script.')

a = np.array(Image.open(SRC).convert('RGB')).astype(np.float32)
rgba, pieza = recortar(a, T)
print('cobertura de la pieza: %.1f%%' % (100.0 * pieza.mean()))
al = rgba[:, :, 3].astype(np.float32)
print('borde: %d px opacos, %d en transicion' % ((al >= 250).sum(), ((al > 10) & (al < 250)).sum()))
Image.fromarray(rgba, 'RGBA').save(OUT)
print('guardado', OUT)
