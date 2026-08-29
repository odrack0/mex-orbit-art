#!/usr/bin/env python3
"""Deriva el ALFA de un atlas de nubes generado sobre NEGRO y le impone el
margen transparente por celda.

Por que existe: los generadores no dan alfa gradual fiable para gas volumetrico
(dan recortes duros o halos), y el margen de 120 px es justo el tipo de
instruccion que ignoran. Sobre negro cualquier IA rinde perfecto, y para una
nube que EMITE luz el alfa correcto es su propia luminancia: hay nube donde hay
brillo. El margen se impone aqui por codigo, celda a celda, garantizado.

Uso:
    py tools/nebula-alpha.py source/renders/nebula-mid-atlas.png \
        ../mex-orbit-client/assets/world/layers/nebula-mid-atlas.png [grid] [margen]

    grid   = lado de la rejilla de variantes (defecto 2 -> 2x2)
    margen = pixeles del fundido a alfa 0 en el borde de CADA celda (defecto 120)

Imprime la cobertura de alfa por celda: una celda con <2% de alfa util es una
variante vacia (regenerar); >60% es una nube que invade el margen (el fundido
la esta recortando: regenerar mas centrada).
"""
import sys

import numpy as np
from PIL import Image


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    entrada, salida = sys.argv[1], sys.argv[2]
    grid = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    margen = int(sys.argv[4]) if len(sys.argv) > 4 else 120

    img = np.asarray(Image.open(entrada).convert("RGB"), dtype=np.float32) / 255.0
    alto, ancho, _ = img.shape
    if alto % grid or ancho % grid:
        print(f"RECHAZAR: {ancho}x{alto} no es divisible por la rejilla {grid}")
        return 1
    ca, cw = alto // grid, ancho // grid

    # alfa = luminancia (gas que emite): suave por construccion, sin halos
    lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]

    # el margen por CELDA: rampa suave (smoothstep) de 0 en el borde a 1 al
    # terminar el margen, en las cuatro direcciones de cada celda
    rampa_y = np.ones(ca, dtype=np.float32)
    rampa_x = np.ones(cw, dtype=np.float32)
    for i in range(margen):
        t = i / margen
        s = t * t * (3.0 - 2.0 * t)
        rampa_y[i] = min(rampa_y[i], s)
        rampa_y[ca - 1 - i] = min(rampa_y[ca - 1 - i], s)
        rampa_x[i] = min(rampa_x[i], s)
        rampa_x[cw - 1 - i] = min(rampa_x[cw - 1 - i], s)
    marco_celda = np.outer(rampa_y, rampa_x)
    marco = np.tile(marco_celda, (grid, grid))

    alfa = lum * marco

    # el color se conserva tal cual (la nube ya viene "iluminada"); donde el
    # alfa es 0 el color da igual, pero se limpia para que el PNG comprima
    rgb = np.where(alfa[..., None] > 0.003, img, 0.0)
    out = np.dstack([rgb, alfa[..., None]])
    Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), "RGBA").save(salida)

    print(f"OK -> {salida}  ({ancho}x{alto}, rejilla {grid}x{grid}, margen {margen}px)")
    for cy in range(grid):
        for cx in range(grid):
            celda = alfa[cy * ca:(cy + 1) * ca, cx * cw:(cx + 1) * cw]
            util = float((celda > 0.06).mean()) * 100.0
            aviso = ""
            if util < 2.0:
                aviso = "  <- VACIA: regenerar esta variante"
            elif util > 60.0:
                aviso = "  <- INVADE el margen: regenerar mas centrada"
            print(f"  celda ({cx},{cy}): {util:5.1f}% de alfa util  p99={np.percentile(celda, 99):.3f}{aviso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
