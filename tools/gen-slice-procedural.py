# -*- coding: utf-8 -*-
"""Genera los assets procedurales del vertical slice (E2).

Produce (rutas relativas a la raiz del repo):
  world/backgrounds/map-1-1.png       fondo prerenderizado del mapa 1-1 (2048x1260, ratio 1.625)
  world/backgrounds/starfield-tile.png  tile repetible de estrellas para el parallax (1024x1024)
  fx/laser-cyan.png / fx/laser-red.png  haz de laser aditivo (256x24)
  fx/explosion-sheet.png              hoja de 8 frames de explosion (8 x 128x128)

Todo es determinista (semilla fija): regenerar produce bytes identicos.
Uso:  py -3 tools/gen-slice-procedural.py
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMILLA = 20260825


def _ruido_valor(ancho, alto, celdas, rng):
    """Ruido de valor bilineal en [0,1] con rejilla de `celdas` puntos."""
    rejilla = [[rng.random() for _ in range(celdas + 2)] for _ in range(celdas + 2)]
    img = [[0.0] * ancho for _ in range(alto)]
    for y in range(alto):
        gy = y / alto * celdas
        y0 = int(gy); fy = gy - y0
        fy = fy * fy * (3 - 2 * fy)
        for x in range(ancho):
            gx = x / ancho * celdas
            x0 = int(gx); fx = gx - x0
            fx = fx * fx * (3 - 2 * fx)
            a = rejilla[y0][x0] * (1 - fx) + rejilla[y0][x0 + 1] * fx
            b = rejilla[y0 + 1][x0] * (1 - fx) + rejilla[y0 + 1][x0 + 1] * fx
            img[y][x] = a * (1 - fy) + b * fy
    return img


def _ruido_fractal(ancho, alto, octavas, rng):
    total = [[0.0] * ancho for _ in range(alto)]
    amplitud, suma = 1.0, 0.0
    for o in range(octavas):
        capa = _ruido_valor(ancho, alto, 3 * (2 ** o), rng)
        for y in range(alto):
            fila_t, fila_c = total[y], capa[y]
            for x in range(ancho):
                fila_t[x] += fila_c[x] * amplitud
        suma += amplitud
        amplitud *= 0.55
    for y in range(alto):
        fila = total[y]
        for x in range(ancho):
            fila[x] /= suma
    return total


def fondo_mapa(ancho=2048, alto=1260):
    """Nebulosa fria (cian/violeta, identidad N) sobre negro espacial, con estrellas."""
    rng = random.Random(SEMILLA)
    # la nebulosa se calcula a cuarto de resolucion y se escala: el ruido es caro en Python puro
    na, nh = ancho // 4, alto // 4
    ruido = _ruido_fractal(na, nh, 5, rng)
    neb = Image.new('RGB', (na, nh))
    px = neb.load()
    for y in range(nh):
        for x in range(na):
            v = ruido[y][x]
            v = max(0.0, (v - 0.42)) ** 1.6  # solo las crestas del ruido son nube
            # dos nubes tintadas por posicion: cian arriba-derecha, violeta abajo-izquierda
            t = (x / na + (1 - y / nh)) / 2
            r = int(v * (30 + 100 * (1 - t)))
            g = int(v * (40 + 60 * t))
            b = int(v * (90 + 110 * t))
            base = 7 + int(3 * ruido[y][x])  # fondo #07070F aprox con variacion sutil
            px[x, y] = (min(255, base + r), min(255, base + g), min(255, 15 + b))
    neb = neb.resize((ancho, alto), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2))

    dib = ImageDraw.Draw(neb)
    # estrellas: tres capas de densidad/brillo
    for cantidad, brillo_max, radio_max in ((900, 110, 1), (260, 190, 1), (60, 255, 2)):
        for _ in range(cantidad):
            x, y = rng.randrange(ancho), rng.randrange(alto)
            b = rng.randint(brillo_max // 2, brillo_max)
            r = rng.randint(1, radio_max)
            tinte = rng.choice([(b, b, b), (b - 20, b - 8, b), (b, b - 10, b - 25)])
            dib.ellipse((x - r, y - r, x + r, y + r), fill=tinte)
    # unas pocas estrellas con destello en cruz
    for _ in range(14):
        x, y = rng.randrange(ancho), rng.randrange(alto)
        b = rng.randint(200, 255)
        for d in range(1, 7):
            a = int(b * (1 - d / 7))
            for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                if 0 <= x + dx < ancho and 0 <= y + dy < alto:
                    dib.point((x + dx, y + dy), fill=(a, a, min(255, a + 20)))
        dib.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(b, b, 255))
    return neb


def tile_estrellas(lado=1024):
    """Tile repetible: cada estrella se pinta modulo el lado para que el borde empalme."""
    rng = random.Random(SEMILLA + 1)
    img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    dib = ImageDraw.Draw(img)
    for cantidad, brillo_max in ((420, 120), (120, 200), (30, 255)):
        for _ in range(cantidad):
            x, y = rng.randrange(lado), rng.randrange(lado)
            b = rng.randint(brillo_max // 2, brillo_max)
            for dx in (-lado, 0, lado):
                for dy in (-lado, 0, lado):
                    if -2 <= x + dx <= lado + 2 and -2 <= y + dy <= lado + 2:
                        dib.point((x + dx, y + dy), fill=(b, b, min(255, b + 15), b))
    return img


def laser(color, largo=256, grosor=24):
    """Haz aditivo: nucleo blanco + halo del color. Pensado para blend ADD en Godot."""
    img = Image.new('RGBA', (largo, grosor), (0, 0, 0, 0))
    px = img.load()
    cy = grosor / 2
    for y in range(grosor):
        dy = abs(y - cy + 0.5) / cy
        halo = max(0.0, 1 - dy) ** 2.2
        nucleo = max(0.0, 1 - dy * 3.2) ** 2
        for x in range(largo):
            # atenuacion suave en las puntas
            dx = min(x, largo - 1 - x) / (largo * 0.12)
            punta = min(1.0, dx)
            a = halo * punta
            r = int((color[0] * a + 255 * nucleo * punta) / (1 + nucleo * punta) if a + nucleo > 0 else 0)
            g = int((color[1] * a + 255 * nucleo * punta) / (1 + nucleo * punta) if a + nucleo > 0 else 0)
            b = int((color[2] * a + 255 * nucleo * punta) / (1 + nucleo * punta) if a + nucleo > 0 else 0)
            alfa = int(255 * min(1.0, a + nucleo * punta))
            px[x, y] = (min(255, r), min(255, g), min(255, b), alfa)
    return img


def _rampa_fuego(calor):
    """calor 0..1 -> color de fuego: rojo oscuro -> naranja -> amarillo -> blanco."""
    calor = max(0.0, min(1.0, calor))
    if calor > 0.85:
        f = (calor - 0.85) / 0.15
        return (255, int(230 + 25 * f), int(140 + 115 * f))
    if calor > 0.55:
        f = (calor - 0.55) / 0.30
        return (255, int(150 + 80 * f), int(30 + 110 * f))
    if calor > 0.25:
        f = (calor - 0.25) / 0.30
        return (int(200 + 55 * f), int(60 + 90 * f), int(10 + 20 * f))
    f = calor / 0.25
    return (int(70 + 130 * f), int(15 + 45 * f), int(5 + 5 * f))


def hoja_explosion(frames=8, lado=128):
    """Bola de fuego con contorno irregular (ruido angular por frame) que se apaga a humo."""
    rng = random.Random(SEMILLA + 2)
    hoja = Image.new('RGBA', (lado * frames, lado), (0, 0, 0, 0))
    chispas = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.5, 1.05)) for _ in range(22)]
    # ruido angular: armonicos fijos para que el contorno evolucione coherente entre frames
    arm = [(rng.randint(3, 9), rng.uniform(0, 2 * math.pi), rng.uniform(0.06, 0.16)) for _ in range(4)]
    for f in range(frames):
        t = f / (frames - 1)          # 0..1
        img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
        px = img.load()
        c = lado / 2
        radio = (0.16 + 0.80 * (t ** 0.6)) * c        # expande rapido y frena
        vida = 1 - t                                   # energia restante
        for y in range(lado):
            for x in range(lado):
                dx, dy = x - c, y - c
                dist = math.hypot(dx, dy)
                ang = math.atan2(dy, dx)
                # contorno irregular: el radio efectivo varia con el angulo y crece con t
                irr = sum(a * math.sin(n * ang + fase + t * 2.2) for n, fase, a in arm)
                d = dist / (radio * (1 + irr * (0.4 + 0.6 * t)))
                if d > 1.0:
                    continue
                nucleo = max(0.0, 1 - d) ** 1.5
                calor = nucleo * (0.55 + 0.45 * vida) + (0.35 * vida if d < 0.35 else 0)
                r, g, b = _rampa_fuego(calor)
                # al final el fuego se enfria a humo grisaceo
                humo = t * t
                r = int(r * (1 - humo) + 90 * humo)
                g = int(g * (1 - humo) + 85 * humo)
                b = int(b * (1 - humo) + 82 * humo)
                a = int(255 * min(1.0, nucleo * 1.8) * (1 - t * 0.75))
                if a > 3:
                    px[x, y] = (r, g, b, a)
        dib = ImageDraw.Draw(img)
        for ang, vel in chispas:
            dch = radio * vel * (0.55 + 0.6 * t)
            x = c + math.cos(ang) * dch
            y = c + math.sin(ang) * dch
            a = int(255 * (1 - t) ** 1.5)
            if a > 10 and 0 <= x < lado and 0 <= y < lado:
                dib.line((x, y, x - math.cos(ang) * 3, y - math.sin(ang) * 3),
                         fill=(255, 210, 120, a), width=1)
        # el primer frame lleva un destello blanco central
        if f == 0:
            for rr, aa in ((10, 255), (16, 140), (24, 60)):
                dib.ellipse((c - rr, c - rr, c + rr, c + rr), fill=None,
                            outline=(255, 255, 240, aa))
            dib.ellipse((c - 8, c - 8, c + 8, c + 8), fill=(255, 255, 240, 255))
        hoja.paste(img, (f * lado, 0))
    return hoja


def guardar(img, ruta):
    destino = os.path.join(RAIZ, ruta)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    img.save(destino, optimize=True)
    print(f'{ruta}  {os.path.getsize(destino) // 1024} KB')


if __name__ == '__main__':
    print('Generando assets procedurales del slice...')
    guardar(fondo_mapa(), 'world/backgrounds/map-1-1.png')
    guardar(tile_estrellas(), 'world/backgrounds/starfield-tile.png')
    guardar(laser((0, 229, 255)), 'fx/laser-cyan.png')
    guardar(laser((255, 61, 110)), 'fx/laser-red.png')
    guardar(hoja_explosion(), 'fx/explosion-sheet.png')
    print('Listo.')
