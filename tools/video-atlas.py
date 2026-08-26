# -*- coding: utf-8 -*-
"""Vídeo en bucle -> atlas de fotogramas para los aliens animados.

**Segundo tipo de asset del catálogo.** Los bichos corrientes son un PNG con
shaders encima (barato, y en el 1-1 hay quince Vex); los de arriba de la
escalera llevan animación de verdad. El coste alto recae justo sobre los que
casi no se repiten — hay dos Skarnox y tres Gravon —, así que la jerarquía del
bestiario decide sola el tipo de asset.

Es lo que hacía el cliente original con sus aliens (`loopPlay`), con una
diferencia: los suyos por eso NO rotaban. Los nuestros sí, porque en Godot el
bucle es contenido y el rumbo lo pone el nodo.

El vídeo debe cumplir el contrato de render (`prompts/README.md`) MÁS dos cosas:
  · **croma verde**, no negro — sobre negro, un casco de metal oscuro no se puede
    separar del fondo, y ese fue el primer intento fallido;
  · **bucle**: el último fotograma tiene que casar con el primero. El script mide
    el salto de la costura contra el paso normal entre fotogramas y avisa. Eso NO
    se arregla después: se arregla pidiéndoselo al generador.

El vídeo fuente se versiona en `source/renders/<Nombre>.mp4`, igual que los
renders fijos: el master canónico vive en el repo, no en la carpeta de descargas
de nadie. Sin él no se puede reexportar a otros fps ni a otra resolución.

La celda puede ser cuadrada ("384") o rectangular ("128x512"). Para un bicho
alargado la segunda ahorra muchisimo: cuadrar al Vorax desperdicia el 80% de
cada celda.

**La celda se elige por el `screen_size` del bicho, no copiando la del anterior.**
Es la leccion del Gravit: mide 124 px en pantalla, asi que la 384 del Gravon
seria triple muestreo pagado entero en VRAM. Con 256 cuesta 12,2 MB en vez de
27,6 — la mitad del presupuesto de esa ronda, ahorrada mirando un numero que ya
estaba en el JSON. Un factor de ~2x sobre el tamanio en pantalla va sobrado.

Con RANGO=ini:fin se exporta solo ese tramo COMO SECUENCIA, no como bucle: es
lo que necesita el portal, que reposa en su primer fotograma y reproduce el
encendido entero una vez al activarlo.

Uso:  py -3 tools/video-atlas.py <video.mp4> <salida.png> [fps] [celda] [croma]
Ej.:  py -3 tools/video-atlas.py source/renders/Gravon.mp4 exports/gravon-anim.png 12 384
      py -3 tools/video-atlas.py source/renders/Vorax.mp4 exports/vorax-anim.png 12 128x512
      RANGO=0:24 py -3 tools/video-atlas.py source/renders/Portal.mp4 exports/portal-anim.png 12 384
"""
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image
from scipy.ndimage import binary_closing, binary_fill_holes, gaussian_filter, label

VIDEO = sys.argv[1]
SALIDA = sys.argv[2]
FPS = int(sys.argv[3]) if len(sys.argv) > 3 else 12
# Celda del atlas: "384" (cuadrada) o "128x512". Las celdas NO tienen por que ser
# cuadradas — Sprite2D parte la textura en hframes x vframes iguales, y punto.
# Para un bicho alargado la diferencia es enorme: cuadrar al Vorax (125x638)
# desperdicia el 80% de cada celda.
_celda = sys.argv[4] if len(sys.argv) > 4 else '384'
if 'x' in _celda.lower():
    LADO_W, LADO_H = (int(v) for v in _celda.lower().split('x'))
else:
    LADO_W = LADO_H = int(_celda)
T = float(sys.argv[5]) if len(sys.argv) > 5 else 22.0


def recortar(a):
    """El mismo criterio que chroma-key.py, en memoria y sin el despill pesado."""
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    greenness = g - np.maximum(r, b)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    # la sombra proyectada es el mismo verde oscurecido: el verdor RELATIVO la caza
    bg = (greenness > T) | (greenness / np.maximum(lum, 1.0) > 0.25)
    pieza = binary_closing(~bg, np.ones((3, 3)))
    # rellenar solo huecos pequenos: uno grande es fondo legitimo visible a traves
    filled = binary_fill_holes(pieza)
    lab_h, nh = label(filled & ~pieza)
    if nh:
        tam = np.bincount(lab_h.ravel())
        tam[0] = 0
        pieza = pieza | np.isin(lab_h, np.where((tam > 0) & (tam < 2500))[0])
    lab, n = label(pieza)
    if n > 1:
        tam = np.bincount(lab.ravel())
        tam[0] = 0
        pieza = np.isin(lab, np.where(tam >= max(24, int(0.00004 * pieza.size)))[0])
    # despill: el verde que queda sobre el casco se recorta al nivel de r/b
    out = a.copy()
    exceso = np.maximum(0.0, g - np.maximum(r, b))
    out[:, :, 1] = g - exceso * 0.92
    out[:, :, 0] = np.minimum(255, out[:, :, 0] + exceso * 0.30)
    out[:, :, 2] = np.minimum(255, out[:, :, 2] + exceso * 0.30)
    alpha = np.clip((gaussian_filter(pieza.astype(np.float32), 0.8) - 0.35) / 0.4, 0, 1) * 255
    return np.dstack([np.clip(out, 0, 255), alpha]).astype(np.uint8), pieza


tmp = tempfile.mkdtemp(prefix='vatlas_')
subprocess.run(['ffmpeg', '-v', 'error', '-i', VIDEO, '-vf', 'fps=%d' % FPS,
                os.path.join(tmp, 'f%04d.png')], check=True)
archivos = sorted(os.listdir(tmp))
print('fotogramas extraidos: %d a %d fps' % (len(archivos), FPS))

# ---- RANGO: secuencia de un disparo en vez de bucle ----
# No todo asset animado es un bucle. El portal es una SECUENCIA: reposo en el
# fotograma 0, y al activarlo se reproduce entera una vez mientras el server
# resuelve el salto de sector. Ahi no hay costura que cerrar —nadie vuelve al
# principio— asi que toda la maquinaria de bucle sobra y estorba: el recorte al
# mejor cierre le comeria justo el final, que es el fotograma en el que el
# portal se queda.
#
# Con RANGO=ini:fin se queda ese tramo y se salta el analisis de bucle. El
# recorte va ANTES de la caja de la union a proposito: encuadrar contando
# fotogramas que se van a tirar agranda la caja y encoge al bicho en la celda.
RANGO = os.environ.get('RANGO', '')
UN_DISPARO = bool(RANGO)
if UN_DISPARO:
    _i, _f = (int(v) for v in RANGO.split(':'))
    archivos = archivos[_i:_f + 1]
    print('RANGO %d:%d -> %d fotogramas · secuencia de un disparo, sin analisis de bucle'
          % (_i, _f, len(archivos)))

# ---- recorte de todos, y caja de la UNION ----
# La caja se calcula sobre TODOS los fotogramas, no sobre el primero: el bicho
# bascula durante el bucle y encuadrar por uno solo le corta un borde en otros.
rgbas, piezas = [], []
for nombre in archivos:
    a = np.array(Image.open(os.path.join(tmp, nombre)).convert('RGB')).astype(np.float32)
    rgba, pieza = recortar(a)
    rgbas.append(rgba)
    piezas.append(pieza)
union = np.any(np.stack(piezas), axis=0)
ys, xs = np.where(union)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
# el recorte toma la PROPORCION de la celda y se agranda hasta contener la union
aspecto = LADO_W / float(LADO_H)
w_src = int((x1 - x0) * 1.06)
h_src = int((y1 - y0) * 1.06)
if w_src / float(h_src) < aspecto:
    w_src = int(h_src * aspecto)
else:
    h_src = int(w_src / aspecto)
print('caja de la union: %d,%d -> %d,%d   recorte %dx%d (celda %dx%d)'
      % (x0, y0, x1, y1, w_src, h_src, LADO_W, LADO_H))

# ---- mejor punto de bucle ----
# El vídeo casi nunca cierra exacto; se prueba a soltar los últimos fotogramas y
# se elige el corte cuyo salto sea menor.
def gris(rgba):
    return (rgba[:, :, :3].mean(axis=2) * (rgba[:, :, 3] / 255.0))


g0 = gris(rgbas[0])
n = len(rgbas)
consec = float(np.mean([np.abs(gris(rgbas[i + 1]) - gris(rgbas[i])).mean()
                        for i in range(min(10, n - 1))]))
salto0 = float(np.abs(gris(rgbas[n - 1]) - g0).mean())
if UN_DISPARO:
    print('secuencia: %d fotogramas · %.1f s a %d fps · el salto 0->fin (%.2f) da igual: '
          'no se vuelve al principio' % (n, n / float(FPS), FPS, salto0))
else:
    print('bucle crudo: %d fotogramas · salto %.2f/255 (paso normal %.2f)' % (n, salto0, consec))

# ---- 1. RECORTE al mejor cierre ----
# Un video casi nunca dura EXACTAMENTE un ciclo: suele pasarse un poco. Soltar
# esos fotogramas de mas cierra el bucle sin inventar nada.
#
# Cuando funciona y cuando no, medido en los dos casos reales:
#   · Skarnox: 48 fotogramas saltaban 13x el paso normal; recortando a 42, 3,5x.
#     El video se pasaba de ciclo y sobraba material -> recortar ARREGLA.
#   · Gravon: 49 fotogramas saltaban 4x; el mejor recorte apenas bajaba a 3,5x
#     perdiendo 6 fotogramas. El video ERA un ciclo entero que no cerraba
#     (rotacion neta de los aros) -> recortar solo quita movimiento real.
#   · Gravit: 48 fotogramas saltaban 4,12 con paso normal 1,18; recortando a 45,
#     1,28 = 1,1x el paso normal. El mejor bucle de un bicho hasta ahora.
#   · Mordax: 4,44 con paso normal 3,16 = 1,4x, y el mejor recorte solo bajaba a
#     3,26 perdiendo 7. Se deja entero: 1,4x ya no se ve.
# Por eso solo se aplica si la mejora es GRANDE; si no, se deja entero y se avisa.
mejor = min(((float(np.abs(gris(rgbas[k - 1]) - g0).mean()), k)
             for k in range(int(n * 0.72), n + 1)), key=lambda t: t[0])
if UN_DISPARO:
    pass
elif mejor[0] < salto0 * 0.6 and mejor[1] < n:
    print('recortado al mejor cierre: %d -> %d fotogramas · salto %.2f (era %.2f)'
          % (n, mejor[1], mejor[0], salto0))
    rgbas = rgbas[:mejor[1]]
    n, salto0 = mejor[1], mejor[0]
else:
    print('sin recorte: el mejor cierre (%.2f en %d) no compensa perder %d fotogramas'
          % (mejor[0], mejor[1], n - mejor[1]))
if not UN_DISPARO:
    print('costura final: %.2f/255 = %.1f veces el paso normal' % (salto0, salto0 / max(consec, 1e-6)))

# ---- 2. CIERRE POR FUNDIDO (apagado por defecto). ----
#
# Dos tecnicas descartadas y por que, que es lo que hay que recordar:
#
# · PING-PONG (reproducir de ida y vuelta) cerraria el bucle gratis, pero aqui
#   no vale: las bandas interiores tienen rotacion NETA (+60 y -32 grados por
#   ciclo), asi que al reves se mecerian en vez de girar.
#
# · FUNDIDO de la cola sobre la cabeza solo sirve si el video dura MAS de un
#   ciclo y sobra material. Cuando el video ES un ciclo entero que no cierra
#   —este caso—, solapar quita movimiento real: el salto bajo de 2.96 a 2.28
#   mientras se perdian 6 fotogramas. Peor negocio.
#
# La discrepancia esta en la rotacion de los aros y no se cierra componiendo en
# 2D: se arregla al GENERAR, pidiendo que el ultimo fotograma case con el
# primero. Con CROSSFADE=n se puede forzar el fundido si el video lo permite.
CF = int(os.environ.get('CROSSFADE', '0'))
if CF and not UN_DISPARO and salto0 > consec * 2.0 and n > CF * 3:
    L = n - CF
    for i in range(CF):
        t = (i + 1) / float(CF + 1)          # 0 = cola pura, 1 = cabeza pura
        cab = rgbas[i].astype(np.float32)
        col = rgbas[L + i].astype(np.float32)
        rgbas[i] = (cab * t + col * (1.0 - t)).astype(np.uint8)
    n = L
    salto = float(np.abs(gris(rgbas[n - 1]) - gris(rgbas[0])).mean())
    print('cerrado con fundido de %d fotogramas: %d finales · salto %.2f/255' % (CF, n, salto))
    if salto > consec * 2.0:
        print('  AVISO: aun salta — subir CROSSFADE')

# ---- atlas ----
cols = math.ceil(math.sqrt(n))
filas = math.ceil(n / cols)
atlas = Image.new('RGBA', (cols * LADO_W, filas * LADO_H), (0, 0, 0, 0))
for i in range(n):
    im = Image.fromarray(rgbas[i], 'RGBA').crop(
        (cx - w_src // 2, cy - h_src // 2, cx + w_src // 2, cy + h_src // 2))
    atlas.paste(im.resize((LADO_W, LADO_H), Image.LANCZOS),
                ((i % cols) * LADO_W, (i // cols) * LADO_H))
os.makedirs(os.path.dirname(SALIDA) or '.', exist_ok=True)
atlas.save(SALIDA, optimize=True)
print('guardado %s  %dx%d  (%d cols x %d filas, celda %dx%d)'
      % (SALIDA, atlas.width, atlas.height, cols, filas, LADO_W, LADO_H))
print('VRAM RGBA8: %.1f MB' % (atlas.width * atlas.height * 4 / 1048576))
print()
print('JSON del bicho:  "frames": { "atlas": "res://...", "hframes": %d, "vframes": %d, '
      '"count": %d, "fps": %d }' % (cols, filas, n, FPS))
