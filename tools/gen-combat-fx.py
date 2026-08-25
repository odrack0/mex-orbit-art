# -*- coding: utf-8 -*-
"""Arte de combate: haces de laser e impactos. Todo BLANCO y tintable en el
juego, para que cada municion defina su color en su JSON (data/ammo/).

Formas heredadas del original (medidas de sus sheets): el haz normal es un
huso horizontal de ~78x12 con nucleo claro, y el "skilled" (con perfil de
piloto) es el mismo mas grueso y brillante (~78x20, grosor 14 vs 8).

  exports/fx/beam.png          haz normal 156x24 (x2 para nitidez)
  exports/fx/beam-skilled.png  haz grueso 156x40
  exports/fx/hull-impact.png   8 frames de 96: chispazo en el casco
  exports/fx/shield-impact.png 8 frames de 128: onda hexagonal en el escudo

Uso:  py -3 tools/gen-combat-fx.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAL = os.path.join(RAIZ, 'exports', 'fx')


def haz(largo=156, alto=24, grosor_rel=0.34, nucleo_rel=0.42):
    """Huso horizontal: se afila en las puntas y tiene el corazon claro.
    grosor_rel: fraccion del alto que ocupa el haz. nucleo_rel: cuanto del
    haz es nucleo blanco (el resto es el color tintado)."""
    img = Image.new('RGBA', (largo, alto), (0, 0, 0, 0))
    px = img.load()
    cy = alto / 2
    semi = alto * grosor_rel
    for x in range(largo):
        t = x / (largo - 1)
        # huso: maximo al centro, afilado en ambas puntas
        perfil_x = math.sin(math.pi * t) ** 0.55
        radio = semi * perfil_x
        if radio < 0.4:
            continue
        for y in range(alto):
            d = abs(y - cy) / radio
            if d > 1.0:
                continue
            cuerpo = (1.0 - d * d) ** 1.5
            nucleo = max(0.0, (1.0 - d / nucleo_rel)) ** 1.4
            # el canal G marca el nucleo (el juego lo usa para mezclar blanco)
            v = int(255 * min(1.0, cuerpo))
            n = int(255 * min(1.0, nucleo))
            px[x, y] = (255, 255, 255, max(v, n))
            # el nucleo se guarda como sobre-alfa: mas opaco al centro
    return img.filter(ImageFilter.GaussianBlur(0.7))


def impacto_casco(lado=96, frames=8):
    """Chispazo: destello con esquirlas que se expande y apaga."""
    hoja = Image.new('RGBA', (lado * frames, lado), (0, 0, 0, 0))
    rng = [(i * 2.399963, 0.35 + (i % 5) * 0.13) for i in range(14)]  # angulo aureo
    for f in range(frames):
        t = f / (frames - 1)
        img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = lado / 2
        # nucleo del impacto
        r = (0.10 + 0.30 * t) * c
        a = int(255 * (1 - t) ** 1.3)
        if a > 4:
            for k in (1.0, 0.6, 0.3):
                rr = r * k
                d.ellipse((c - rr, c - rr, c + rr, c + rr),
                          fill=(255, 255, 255, int(a * (0.35 + 0.65 * (1 - k)))))
        # esquirlas
        for ang, vel in rng:
            dist = c * 0.85 * vel * (0.3 + 1.1 * t)
            x = c + math.cos(ang) * dist
            y = c + math.sin(ang) * dist
            aa = int(230 * (1 - t) ** 1.8)
            if aa > 8:
                d.line((c + math.cos(ang) * dist * 0.75, c + math.sin(ang) * dist * 0.75, x, y),
                       fill=(255, 255, 255, aa), width=2)
        hoja.paste(img.filter(ImageFilter.GaussianBlur(0.9)), (f * lado, 0))
    return hoja


def impacto_escudo(lado=128, frames=8):
    """Onda hexagonal: la celda del escudo que absorbe el golpe."""
    hoja = Image.new('RGBA', (lado * frames, lado), (0, 0, 0, 0))
    for f in range(frames):
        t = f / (frames - 1)
        img = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = lado / 2
        # el hexagono crece y se desvanece; el borde brilla mas
        r = (0.30 + 0.55 * t) * c
        a = int(255 * (1 - t) ** 1.4)
        if a > 4:
            pts = [(c + r * math.cos(math.pi / 6 + i * math.pi / 3),
                    c + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
            d.polygon(pts, fill=(255, 255, 255, int(a * 0.18)))
            d.line(pts + [pts[0]], fill=(255, 255, 255, a), width=max(1, int(4 * (1 - t) + 1)))
            # celdas internas insinuadas
            if t < 0.6:
                r2 = r * 0.55
                pts2 = [(c + r2 * math.cos(math.pi / 6 + i * math.pi / 3),
                         c + r2 * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
                d.line(pts2 + [pts2[0]], fill=(255, 255, 255, int(a * 0.55)), width=1)
        hoja.paste(img.filter(ImageFilter.GaussianBlur(1.0)), (f * lado, 0))
    return hoja


if __name__ == '__main__':
    os.makedirs(SAL, exist_ok=True)
    piezas = [
        ('beam.png', haz(156, 24, 0.30, 0.40)),
        ('beam-skilled.png', haz(156, 40, 0.36, 0.50)),
        ('hull-impact.png', impacto_casco()),
        ('shield-impact.png', impacto_escudo()),
    ]
    for nombre, img in piezas:
        ruta = os.path.join(SAL, nombre)
        img.save(ruta, optimize=True)
        print(f'fx/{nombre}  {img.size[0]}x{img.size[1]}  {os.path.getsize(ruta) // 1024} KB')
