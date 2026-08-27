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

  py -3 tools/gen-normal.py <entrada.png> <salida.png> [grados] [macro] [detalle] [sigma]
"""
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter, sobel

SRC, OUT = sys.argv[1], sys.argv[2]
OBJETIVO = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
MACRO = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
DET = float(sys.argv[5]) if len(sys.argv) > 5 else 0.55
SIGMA = float(sys.argv[6]) if len(sys.argv) > 6 else 6.0

a = np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float32)
alpha = a[:, :, 3] / 255.0
pieza = alpha > 0.5
if not pieza.any():
    raise SystemExit('la imagen no tiene pieza opaca')

# --- MACRO: hombro circular desde el borde de la silueta ---
# El radio se toma de la propia pieza (no un numero fijo): la distancia maxima al
# borde ES el "grosor" del objeto, asi que un casco ancho sale mas abombado que
# una antena, que es exactamente lo que se quiere.
d = distance_transform_edt(pieza)
radio = max(float(d.max()) * 0.85, 1.0)
t = np.clip(d / radio, 0.0, 1.0)
h_macro = np.sqrt(np.clip(1.0 - (1.0 - t) ** 2, 0.0, 1.0))

# --- DETALLE: luminancia con paso alto ---
lum = (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]) / 255.0
lum = np.where(pieza, lum, 0.0)
h_det = lum - gaussian_filter(lum, SIGMA)
esc = np.percentile(np.abs(h_det[pieza]), 99)
h_det = np.clip(h_det / max(esc, 1e-4), -1.0, 1.0) * 0.5

h = MACRO * h_macro + DET * h_det
h = np.where(pieza, h, 0.0)
# suavizado minimo: sobel sobre altura con ruido de compresion da normales sucias
h = gaussian_filter(h, 0.8)

# --- gradiente -> normal ---
# El eje V de una textura apunta hacia ABAJO, asi que la componente Y se invierte
# respecto a la convencion de toda la vida. Equivocarse aqui no rompe nada: deja
# la luz entrando por el lado contrario, que es el fallo mas dificil de ver y el
# mas facil de arreglar (un signo).
gx = sobel(h, axis=1) / 8.0
gy = sobel(h, axis=0) / 8.0


def normales(k):
    v = np.dstack([-gx * k, gy * k, np.ones_like(h)])
    return v / np.linalg.norm(v, axis=2, keepdims=True)


def inclinacion(k):
    return np.degrees(np.arccos(np.clip(normales(k)[pieza][:, 2], -1, 1))).mean()


# biseccion sobre la fuerza: monotona por construccion (mas k, mas inclinacion),
# asi que no hace falta nada mas listo
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
Image.fromarray(np.dstack([rgb, a[:, :, 3]]).clip(0, 255).astype(np.uint8), 'RGBA').save(OUT)

print('radio del hombro: %.1f px  ·  macro %.2f  detalle %.2f  sigma %.1f' % (radio, MACRO, DET, SIGMA))
print('fuerza resuelta: %.1f  ->  inclinacion media %.1f grados (objetivo %.1f)'
      % (fuerza, inclinacion(fuerza), OBJETIVO))
print('guardado', OUT)
