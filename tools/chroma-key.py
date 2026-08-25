"""Quita el fondo verde de un render y neutraliza el derrame de color sobre el casco."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes, binary_closing, binary_opening, label, gaussian_filter

SRC, OUT = sys.argv[1], sys.argv[2]
T = float(sys.argv[3]) if len(sys.argv) > 3 else 22.0
# Luminancia minima para considerar un pixel "fondo". El croma es brillante; con
# naves oscuras esto evita que un reflejo verde sobre el casco se recorte como fondo.
LMIN = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0

im = Image.open(SRC).convert("RGB")
a = np.array(im).astype(np.float32)
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

# "verdor": cuanto sobresale el verde sobre el MAYOR de rojo y azul.
# Contra la media, un cian brillante (g alto, b alto) puntuaba como verde y
# se recortaba el nucleo/las franjas emisivas; contra el maximo, no.
greenness = g - np.maximum(r, b)
print("verdor  min %.1f  max %.1f  mediana %.1f" % (greenness.min(), greenness.max(), np.median(greenness)))

lum = 0.299 * r + 0.587 * g + 0.114 * b
# La sombra proyectada es el mismo verde pero oscurecido: en valor absoluto pasa el
# umbral, asi que hay que medir el verdor RELATIVO al brillo para descartarla tambien.
ratio = greenness / np.maximum(lum, 1.0)
bg = ((greenness > T) & (lum > LMIN)) | (ratio > 0.25)
ship = ~bg

# limpieza conservadora: cerrar solo huecos pequenos y NO erosionar.
# Una apertura se come antenas, barras y puntas finas del casco.
ship = binary_closing(ship, np.ones((3, 3)))
# Rellenar SOLO huecos pequenos (ruido interior). Un hueco grande es fondo
# legitimo visible a traves de la pieza: el vano de un anillo de atraque,
# el hueco del anillo de la Goliath. Rellenarlo todo convierte ese fondo en "nave".
HOLE_MAX = int(sys.argv[5]) if len(sys.argv) > 5 else 2500
filled = binary_fill_holes(ship)
holes = filled & ~ship
lab_h, nh = label(holes)
if nh:
    hsizes = np.bincount(lab_h.ravel())
    hsizes[0] = 0
    small = np.where((hsizes > 0) & (hsizes < HOLE_MAX))[0]
    ship = ship | np.isin(lab_h, small)
    print("huecos: %d, rellenados (< %d px): %d" % (nh, HOLE_MAX, len(small)))

# conserva toda pieza que no sea ruido, no solo la mayor: hay detalles
# (puntas de gondola, extremos de canon) que quedan separados del cuerpo.
lab, n = label(ship)
if n > 1:
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    keep = np.where(sizes >= max(24, int(0.00004 * ship.size)))[0]
    ship = np.isin(lab, keep)
    print("piezas: %d, conservadas: %d" % (n, len(keep)))
print("cobertura nave: %.1f%%" % (100.0 * ship.mean()))

# despill: si sigue habiendo verde de mas en el casco, se recorta al nivel de r/b
out = a.copy()
excess = np.maximum(0.0, g - np.maximum(r, b))
out[:, :, 1] = g - excess * 0.92
# recupera algo de luminancia perdida al quitar el verde
lift = excess * 0.30
out[:, :, 0] = np.minimum(255, out[:, :, 0] + lift)
out[:, :, 2] = np.minimum(255, out[:, :, 2] + lift)

# alfa con borde suavizado para que el vectorizador no dentelle
alpha = gaussian_filter(ship.astype(np.float32), 0.8)
alpha = np.clip((alpha - 0.35) / 0.4, 0, 1) * 255

rgba = np.dstack([np.clip(out, 0, 255), alpha]).astype(np.uint8)
Image.fromarray(rgba, "RGBA").save(OUT)
print("guardado", OUT)
