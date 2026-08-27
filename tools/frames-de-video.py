# -*- coding: utf-8 -*-
"""Saca los fotogramas de un video de asset, ya sin croma, para elegir poses.

Nace de una necesidad concreta: Meshy congela UNA pose, la de la imagen que le
das. El primer Vexor se genero desde un fotograma con las alas pegadas al cuerpo,
y por eso salio una concha fusionada donde el ala y el flanco son la misma
superficie — no hay nada que abrir. Para tener articulacion hacen falta DOS
modelos, uno de cada extremo del ciclo, y para eso hace falta poder elegir el
fotograma exacto.

Ademas de recortar, MIDE: el ancho de la silueta por fotograma dice cual es el
mas abierto y cual el mas cerrado. Es el mismo criterio con el que se encontro la
bisagra en la malla (el ancho salta donde acaban las placas del torax), aplicado
al video en vez de a la geometria.

Uso:  py -3 tools/frames-de-video.py <video.mp4> <carpeta_salida> [fps] [croma]

Los fotogramas NO se versionan: se regeneran del master en `source/renders/`,
que es el que si esta en git.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from croma import recortar    # noqa: E402

VIDEO = sys.argv[1]
SALIDA = sys.argv[2]
FPS = int(sys.argv[3]) if len(sys.argv) > 3 else 24
T = float(sys.argv[4]) if len(sys.argv) > 4 else 22.0
MARGEN = 0.06        # aire alrededor de la union, en tanto por uno del lado

os.makedirs(SALIDA, exist_ok=True)
tmp = tempfile.mkdtemp()
try:
    subprocess.run(['ffmpeg', '-v', 'error', '-i', VIDEO, '-vf', 'fps=%d' % FPS,
                    os.path.join(tmp, 'f%04d.png')], check=True)
    archivos = sorted(os.listdir(tmp))
    print('fotogramas extraidos: %d a %d fps' % (len(archivos), FPS))

    rgbas, piezas = [], []
    for nombre in archivos:
        a = np.array(Image.open(os.path.join(tmp, nombre)).convert('RGB')).astype(np.float32)
        rgba, pieza = recortar(a, T)
        rgbas.append(rgba)
        piezas.append(pieza)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# Encuadre COMUN a todos: si cada fotograma se recorta a su propia caja, el bicho
# cambia de tamanio entre poses y Meshy recibe dos escalas distintas.
union = np.any(np.stack(piezas), axis=0)
ys, xs = np.where(union)
x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
lado = int(max(x1 - x0, y1 - y0) * (1.0 + 2 * MARGEN))
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2

print('union: %dx%d  ->  lienzo cuadrado de %d' % (x1 - x0, y1 - y0, lado))
print('')
print('  #   ancho   alto   %s' % 'silueta')

anchos = []
for i, (rgba, pieza) in enumerate(zip(rgbas, piezas)):
    fys, fxs = np.where(pieza)
    ancho = int(fxs.max() - fxs.min()) if fxs.size else 0
    alto = int(fys.max() - fys.min()) if fys.size else 0
    anchos.append(ancho)

    lienzo = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    img = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')
    lienzo.paste(img, (lado // 2 - cx, lado // 2 - cy))
    lienzo.save(os.path.join(SALIDA, 'f%03d.png' % (i + 1)))

anchos = np.array(anchos)
rango = anchos.max() - anchos.min()
for i, ancho in enumerate(anchos):
    fys, fxs = np.where(piezas[i])
    alto = int(fys.max() - fys.min()) if fys.size else 0
    barra = '#' * int(30.0 * (ancho - anchos.min()) / max(1, rango))
    marca = ''
    if ancho == anchos.max():
        marca = '  <== EL MAS ABIERTO'
    elif ancho == anchos.min():
        marca = '  <== EL MAS CERRADO'
    print('  %3d  %5d  %5d   %-30s%s' % (i + 1, ancho, alto, barra, marca))

print('')
print('ancho: %d..%d px  (recorrido de %d px, %.0f%% del maximo)'
      % (anchos.min(), anchos.max(), rango, 100.0 * rango / anchos.max()))
print('MAS ABIERTOS : %s' % ', '.join('f%03d' % (i + 1) for i in np.argsort(-anchos)[:3]))
print('MAS CERRADOS : %s' % ', '.join('f%03d' % (i + 1) for i in np.argsort(anchos)[:3]))
print('salida: %s' % SALIDA)
