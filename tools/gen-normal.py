# -*- coding: utf-8 -*-
"""Mapa de normales derivado del propio render. Ruta C del relieve.

El arte del juego es CENITAL y los sprites ROTAN, asi que su iluminacion gira
con ellos: el brillo del casco apunta siempre al mismo sitio *relativo a la
nave*, nunca al mismo sitio del mundo. El ojo lee eso como recorte de papel.

Un mapa de normales arregla justo eso y nada mas: el shader reilumina el sprite
contra una luz fija en el MUNDO, asi que al virar el reflejo barre el casco. No
da volumen —la silueta sigue siendo plana, no hay escorzo—, da relieve.

La altura sale de DOS fuentes que hacen cosas distintas, y mezclarlas en una sola
no funciona:

  · MACRO — la silueta. La distancia al borde dentro de la pieza aproxima un
    cuerpo redondeado: 0 en el contorno, 1 al fondo, con hombro circular. Esto
    es lo que hace que la nave parezca un objeto y no una calcomania.
  · DETALLE — la luminancia PASADA POR ALTO. Las lineas de panel, los remaches
    y los greebles. El paso alto no es un adorno: la luminancia cruda trae
    cocida la iluminacion del render (un degradado suave de arriba a abajo), y
    si entra tal cual, el mapa de normales cree que la nave es una rampa.

El defecto conocido de derivar altura de la luminancia es que **lo claro sube**,
asi que un rotulo pintado se convierte en un bulto. Con un render de arcilla no
pasa —ahi el sombreado ES la forma—; con uno sucio y rotulado, si. Es otra razon
por la que un render limpio vale mas que uno bonito.

La FUERZA no se pasa a mano: se resuelve para que la inclinacion media de la
normal caiga en un objetivo (30 grados por defecto). Un factor fijo da un
resultado distinto en cada asset —depende del contraste del render y del tamanio
del export—, y entonces cada nave se ilumina con una intensidad distinta sin que
nadie sepa por que. El objetivo, en cambio, significa lo mismo en todos.

Con ATLAS=colsxfilas se procesa una rejilla de fotogramas. Cada celda va por su
cuenta —la silueta y el paso alto no pueden cruzar el borde de una celda, ahi
empieza otro bicho— pero **la fuerza se resuelve una sola vez para toda la hoja**.
Si se resolviera por celda, cada fotograma tendria su propia intensidad de
relieve y la criatura parpadearia al animarse.

Con ESCALA=0.5 el mapa sale a media resolucion. Las normales son de frecuencia
mas baja que el color y aguantan bien la reduccion, y en un atlas eso importa: un
mapa a tamanio completo DOBLA la VRAM del asset mas caro que tenemos. A la mitad
cuesta un 25%.

  py -3 tools/gen-normal.py <entrada.png> <salida.png> [grados] [macro] [detalle] [sigma]
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter, sobel

SRC, OUT = sys.argv[1], sys.argv[2]
OBJETIVO = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
MACRO = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
DET = float(sys.argv[5]) if len(sys.argv) > 5 else 0.55
SIGMA = float(sys.argv[6]) if len(sys.argv) > 6 else 6.0
_at = os.environ.get('ATLAS', '')
COLS, FILAS = (int(v) for v in _at.lower().split('x')) if _at else (1, 1)
ESCALA = float(os.environ.get('ESCALA', '1'))

a = np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float32)
H, W = a.shape[0] // FILAS, a.shape[1] // COLS


def altura(celda):
    """Altura de UNA celda: silueta (volumen) + luminancia pasada por alto (detalle)."""
    al = celda[:, :, 3] / 255.0
    pieza = al > 0.5
    if not pieza.any():
        return np.zeros(celda.shape[:2], np.float32), pieza, 0.0

    # MACRO: hombro circular desde el borde. El radio se toma de la propia pieza
    # (no un numero fijo): la distancia maxima al borde ES el "grosor" del objeto,
    # asi que un casco ancho sale mas abombado que una antena.
    d = distance_transform_edt(pieza)
    radio = max(float(d.max()) * 0.85, 1.0)
    t = np.clip(d / radio, 0.0, 1.0)
    h_macro = np.sqrt(np.clip(1.0 - (1.0 - t) ** 2, 0.0, 1.0))

    # DETALLE: luminancia con paso alto
    lum = (0.299 * celda[:, :, 0] + 0.587 * celda[:, :, 1] + 0.114 * celda[:, :, 2]) / 255.0
    lum = np.where(pieza, lum, 0.0)
    h_det = lum - gaussian_filter(lum, SIGMA)
    esc = np.percentile(np.abs(h_det[pieza]), 99)
    h_det = np.clip(h_det / max(esc, 1e-4), -1.0, 1.0) * 0.5

    h = np.where(pieza, MACRO * h_macro + DET * h_det, 0.0)
    # suavizado minimo: sobel sobre altura con ruido de compresion da normales sucias
    return gaussian_filter(h, 0.8).astype(np.float32), pieza, radio


gx = np.zeros(a.shape[:2], np.float32)
gy = np.zeros(a.shape[:2], np.float32)
pieza = np.zeros(a.shape[:2], bool)
radios = []
for f in range(FILAS):
    for c in range(COLS):
        sl = (slice(f * H, (f + 1) * H), slice(c * W, (c + 1) * W))
        h, p, r = altura(a[sl])
        # El eje V de una textura apunta hacia ABAJO, asi que la componente Y se
        # invierte respecto a la convencion de toda la vida. Equivocarse aqui no
        # rompe nada: deja la luz entrando por el lado contrario, que es el fallo
        # mas dificil de ver y el mas facil de arreglar (un signo).
        gx[sl] = sobel(h, axis=1) / 8.0
        gy[sl] = sobel(h, axis=0) / 8.0
        pieza[sl] = p
        if r > 0:
            radios.append(r)
if not pieza.any():
    raise SystemExit('la imagen no tiene pieza opaca')


def normales(k):
    v = np.dstack([-gx * k, gy * k, np.ones_like(gx)])
    return v / np.linalg.norm(v, axis=2, keepdims=True)


def inclinacion(k):
    return np.degrees(np.arccos(np.clip(normales(k)[pieza][:, 2], -1, 1))).mean()


# biseccion sobre la fuerza: monotona por construccion (mas k, mas inclinacion).
# UNA para toda la hoja, o cada fotograma tendria su propia intensidad y la
# criatura parpadearia al animarse.
lo, hi = 0.0, 1.0
while inclinacion(hi) < OBJETIVO and hi < 1e6:
    hi *= 4.0
for _ in range(40):
    med = 0.5 * (lo + hi)
    if inclinacion(med) < OBJETIVO:
        lo = med
    else:
        hi = med
fuerza = 0.5 * (lo + hi)
n = normales(fuerza)

rgb = (n * 0.5 + 0.5) * 255.0
# fuera de la pieza, normal plana: el shader no la mira, pero el filtro bilineal
# de los bordes si, y una normal basura ahi ribetea el contorno al iluminar
plano = np.array([127.5, 127.5, 255.0])
rgb = np.where(pieza[:, :, None], rgb, plano[None, None, :])
salida = Image.fromarray(np.dstack([rgb, a[:, :, 3]]).clip(0, 255).astype(np.uint8), 'RGBA')
if ESCALA != 1.0:
    salida = salida.resize((int(a.shape[1] * ESCALA), int(a.shape[0] * ESCALA)), Image.LANCZOS)
salida.save(OUT)

print('%d celdas de %dx%d  ·  hombro medio %.1f px  ·  macro %.2f detalle %.2f sigma %.1f'
      % (COLS * FILAS, W, H, float(np.mean(radios)), MACRO, DET, SIGMA))
print('salida %s  ·  escala %.2f  ·  VRAM RGBA8 %.1f MB'
      % (str(salida.size), ESCALA, salida.size[0] * salida.size[1] * 4 / 1048576.0))
print('fuerza resuelta: %.1f  ->  inclinacion media %.1f grados (objetivo %.1f)'
      % (fuerza, inclinacion(fuerza), OBJETIVO))
print('guardado', OUT)
