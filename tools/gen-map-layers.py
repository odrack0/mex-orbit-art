# -*- coding: utf-8 -*-
"""Capas procedurales del fondo de mapa (estructura del prototipo, mapa 1-1).

Genera los mosaicos SIN COSTURA de las capas de paralaje y el sol del lensflare:
  exports/map-layers/dust-far.png     tile profundo (pFactor 10, gris azulado tenue)
  exports/map-layers/nebula-mid.png   tile medio (pFactor 6, tinte cian)
  exports/map-layers/nebula-near.png  tile cercano (pFactor 3, violeta, ralo)
  exports/map-layers/sun.png          el sol del destello (radial calido)
  exports/map-layers/flare-ghost.png  fantasma de lente (se tinta en el juego)

Determinista (semilla fija). El fondo PRINCIPAL y los planetas son renders IA
(prompts en prompts/fondo-1-1.md y prompts/planetas.md).

Uso:  py -3 tools/gen-map-layers.py
"""
import math
import os
import random

from PIL import Image, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAL = os.path.join(RAIZ, 'exports', 'map-layers')
SEMILLA = 20260826


def ruido_tileable(lado, celdas, rng):
    """Ruido de valor SIN COSTURA: la rejilla envuelve modulo `celdas`."""
    rejilla = [[rng.random() for _ in range(celdas)] for _ in range(celdas)]
    img = [[0.0] * lado for _ in range(lado)]
    for y in range(lado):
        gy = y / lado * celdas
        y0 = int(gy) % celdas
        y1 = (y0 + 1) % celdas
        fy = gy - int(gy)
        fy = fy * fy * (3 - 2 * fy)
        for x in range(lado):
            gx = x / lado * celdas
            x0 = int(gx) % celdas
            x1 = (x0 + 1) % celdas
            fx = gx - int(gx)
            fx = fx * fx * (3 - 2 * fx)
            a = rejilla[y0][x0] * (1 - fx) + rejilla[y0][x1] * fx
            b = rejilla[y1][x0] * (1 - fx) + rejilla[y1][x1] * fx
            img[y][x] = a * (1 - fy) + b * fy
    return img


def fractal_tileable(lado, octavas, rng):
    total = [[0.0] * lado for _ in range(lado)]
    amplitud, suma = 1.0, 0.0
    for o in range(octavas):
        capa = ruido_tileable(lado, 3 * (2 ** o), rng)
        for y in range(lado):
            ft, fc = total[y], capa[y]
            for x in range(lado):
                ft[x] += fc[x] * amplitud
        suma += amplitud
        amplitud *= 0.55
    for y in range(lado):
        f = total[y]
        for x in range(lado):
            f[x] /= suma
    return total


def tile_nube(lado, tinte, umbral, alfa_max, octavas, semilla_extra):
    rng = random.Random(SEMILLA + semilla_extra)
    ruido = fractal_tileable(lado, octavas, rng)
    img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    px = img.load()
    for y in range(lado):
        for x in range(lado):
            v = max(0.0, ruido[y][x] - umbral) / max(1e-6, 1 - umbral)
            v = v ** 1.7
            if v <= 0.003:
                continue
            a = int(alfa_max * v)
            px[x, y] = (tinte[0], tinte[1], tinte[2], a)
    return img.filter(ImageFilter.GaussianBlur(1.5))


def sol(lado=512):
    img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    px = img.load()
    c = lado / 2
    for y in range(lado):
        for x in range(lado):
            d = math.hypot(x - c, y - c) / c
            if d > 1.0:
                continue
            nucleo = max(0.0, 1 - d * 3.2) ** 1.6
            halo = max(0.0, 1 - d) ** 3.2
            a = min(1.0, nucleo + halo * 0.75)
            r = 255
            g = int(238 * min(1.0, nucleo * 1.4 + halo * 0.85))
            b = int(210 * min(1.0, nucleo * 1.2 + halo * 0.6))
            px[x, y] = (r, g, b, int(255 * a))
    return img


def fantasma(lado=128):
    """Anillo suave para la cadena de lentes; el color lo pone el juego."""
    img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    px = img.load()
    c = lado / 2
    for y in range(lado):
        for x in range(lado):
            d = math.hypot(x - c, y - c) / c
            if d > 1.0:
                continue
            cuerpo = max(0.0, 1 - d) ** 1.4 * 0.45
            anillo = max(0.0, 1 - abs(d - 0.82) * 9) * 0.6
            a = min(1.0, cuerpo + anillo)
            px[x, y] = (255, 255, 255, int(160 * a))
    return img


if __name__ == '__main__':
    os.makedirs(SAL, exist_ok=True)
    piezas = [
        ('dust-far.png', tile_nube(1024, (95, 110, 140), 0.46, 44, 5, 1)),
        ('nebula-mid.png', tile_nube(1024, (60, 175, 200), 0.52, 66, 5, 2)),
        ('nebula-near.png', tile_nube(1024, (140, 110, 220), 0.60, 56, 4, 3)),
        ('sun.png', sol()),
        ('flare-ghost.png', fantasma()),
    ]
    for nombre, img in piezas:
        ruta = os.path.join(SAL, nombre)
        img.save(ruta, optimize=True)
        print(f'map-layers/{nombre}  {os.path.getsize(ruta) // 1024} KB')
