# -*- coding: utf-8 -*-
"""Assets de motor: la llama de tobera y la chispa de estela.

Modelo del prototipo: una LLAMA por tobera anclada a la nave (rota con ella,
crece con el empuje) + estela de CHISPAS soltadas al mundo que se quedan atras.

  exports/fx/engine-flame.png   pluma vertical 64x192, proa arriba: la llama
                                nace en la tobera (arriba) y se afila a la popa
  exports/fx/spark.png          punto redondo suave 32x32 para las particulas

Uso:  py -3 tools/gen-engine-fx.py
"""
import math
import os

from PIL import Image, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAL = os.path.join(RAIZ, 'exports', 'fx')


def llama(ancho=64, alto=192):
    """Pluma vertical: nucleo blanco-cian arriba que se afila y apaga hacia abajo."""
    img = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
    px = img.load()
    cx = ancho / 2
    for y in range(alto):
        t = y / (alto - 1)                     # 0 en la tobera, 1 en la punta
        # el ancho se afila con una curva suave, con un pequeno abultamiento inicial
        radio = cx * (1.0 - t) ** 0.75 * (0.55 + 0.45 * math.sin(min(1.0, t * 4) * math.pi / 2))
        if radio < 0.5:
            continue
        # intensidad: maxima en la boquilla, cae hacia la punta
        fuerza = (1.0 - t) ** 1.35
        for x in range(ancho):
            d = abs(x - cx) / radio
            if d > 1.0:
                continue
            perfil = (1.0 - d * d) ** 1.6      # seccion transversal
            v = perfil * fuerza
            if v <= 0.004:
                continue
            nucleo = max(0.0, (perfil - 0.55) / 0.45) * fuerza   # el corazon claro
            r = int(180 * nucleo + 40 * v)
            g = int(215 * nucleo + 190 * v)
            b = int(255 * nucleo + 255 * v)
            a = int(255 * min(1.0, v * 1.25))
            px[x, y] = (min(255, r), min(255, g), min(255, b), a)
    return img.filter(ImageFilter.GaussianBlur(1.1))


def chispa(lado=32):
    """Punto redondo suave: la particula de la estela (se tinta en el juego)."""
    img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    px = img.load()
    c = lado / 2
    for y in range(lado):
        for x in range(lado):
            d = math.hypot(x - c, y - c) / c
            if d > 1.0:
                continue
            v = (1.0 - d) ** 2.2
            px[x, y] = (255, 255, 255, int(255 * v))
    return img.filter(ImageFilter.GaussianBlur(0.8))


if __name__ == '__main__':
    os.makedirs(SAL, exist_ok=True)
    for nombre, img in [('engine-flame.png', llama()), ('spark.png', chispa())]:
        ruta = os.path.join(SAL, nombre)
        img.save(ruta, optimize=True)
        print(f'fx/{nombre}  {img.size[0]}x{img.size[1]}  {os.path.getsize(ruta) // 1024} KB')
