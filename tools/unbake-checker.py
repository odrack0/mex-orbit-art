"""
Quita un fondo de damero "falsa transparencia" horneado como pixeles reales.

Algunas herramientas exportan el tablero gris/blanco que representa la transparencia
en vez de un canal alfa. Se detecta por ser claro y neutro (sin saturacion), al
contrario que el casco.
"""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes, binary_closing, label, gaussian_filter

SRC, OUT = sys.argv[1], sys.argv[2]
LMIN = float(sys.argv[3]) if len(sys.argv) > 3 else 205.0   # brillo minimo del damero
SMAX = float(sys.argv[4]) if len(sys.argv) > 4 else 0.10    # saturacion maxima del damero

a = np.array(Image.open(SRC).convert("RGB")).astype(np.float32)
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
mx, mn = a.max(axis=2), a.min(axis=2)
sat = np.where(mx > 1, (mx - mn) / np.maximum(mx, 1), 0.0)
lum = 0.299 * r + 0.587 * g + 0.114 * b

bg = (lum > LMIN) & (sat < SMAX)
ship = ~bg

ship = binary_closing(ship, np.ones((3, 3)))
ship = binary_fill_holes(ship)

lab, n = label(ship)
if n > 1:
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    keep = np.where(sizes >= max(24, int(0.00004 * ship.size)))[0]
    ship = np.isin(lab, keep)
    print("piezas: %d, conservadas: %d" % (n, len(keep)))
print("cobertura nave: %.1f%%" % (100.0 * ship.mean()))

alpha = gaussian_filter(ship.astype(np.float32), 0.8)
alpha = np.clip((alpha - 0.35) / 0.4, 0, 1) * 255

Image.fromarray(np.dstack([a, alpha]).astype(np.uint8), "RGBA").save(OUT)
print("guardado", OUT)
