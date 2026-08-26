# -*- coding: utf-8 -*-
"""Exporta los assets del juego desde los renders recortados: PNG DIRECTO.

Dictamen 2026-08-25: el master canonico es el render recortado (source/renders/
*-cut.png); los exports son downscale Lanczos directo — cero perdida. El SVG
vectorizado queda como herramienta opcional de estilo, no como paso del pipeline
(posterizaba el brillo y mordia los contornos).

Tamaños (dial del pipeline): naves y NPCs 512 (aguantan el zoom 3x de camara),
estacion 1024 (es 2x mas grande en pantalla), props 256.

Uso:  py -3 tools/export-png.py
"""
import os
import subprocess
import sys

from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (recorte, export, lado, canal_emisivo o None, umbral)
PIEZAS = [
    ('source/renders/phoenix-cut.png', 'exports/phoenix.png', 512, None, 0),
    ('source/renders/vex-cut.png', 'exports/vex.png', 512, 'r', 18),
    ('source/renders/vexor-cut.png', 'exports/vexor.png', 512, 'r', 18),
    # El Skarn lleva umbral ALTO: sus cristales rosados tambien tiran a rojo y
    # con 12-26 entraban a la capa emisiva, brillando como si fueran magma.
    ('source/renders/skarn-cut.png', 'exports/skarn.png', 512, 'r', 40),
    # Ferox: primer asset CLARO del catalogo. El hueso marfil tiene algo de rojo,
    # asi que el umbral sube para que se enciendan los ojos y las costuras, no el cuerpo.
    ('source/renders/ferox-cut.png', 'exports/ferox.png', 512, 'r', 45),
    ('source/renders/skarnox-cut.png', 'exports/skarnox.png', 512, 'r', 40),
    ('source/renders/gravit-cut.png', 'exports/gravit.png', 512, 'r', 20),
    # Mordax: cuerpo rojo-pardo Y dientes palidos, la peor combinacion para el
    # canal rojo. Umbral alto para que se enciendan la mirada y las costuras,
    # no la dentadura ni el caparazon entero.
    ('source/renders/mordax-cut.png', 'exports/mordax.png', 512, 'r', 50),
    ('source/renders/station-cut.png', 'exports/station.png', 1024, 'c', 16),
    ('source/renders/caja-cut.png', 'exports/cargo-box.png', 256, 'c', 16),
    ('source/renders/portal-cut.png', 'exports/portal.png', 256, 'm', 14),
    ('source/renders/planeta-a-cut.png', 'exports/map-layers/planet-a.png', 512, None, 0),
    ('source/renders/planet-b-cut.png', 'exports/map-layers/planet-b.png', 512, None, 0),
    ('source/renders/planet-c-cut.png', 'exports/map-layers/planet-c.png', 512, None, 0),
]

# el fondo principal es imagen a sangre SIN croma: solo se ajusta a 2048x1280
FONDO = ('source/renders/fondo-1-1.png', 'exports/map-1-1.png', (2048, 1280))


def exportar(rel_in, rel_out, lado):
    img = Image.open(os.path.join(RAIZ, rel_in)).convert('RGBA')
    img = img.resize((lado, lado), Image.LANCZOS)
    destino = os.path.join(RAIZ, rel_out)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    img.save(destino, optimize=True)
    print(f'{rel_out}  {lado}px  {os.path.getsize(destino) // 1024} KB')


for rel_in, rel_out, lado, canal, umbral in PIEZAS:
    if not os.path.exists(os.path.join(RAIZ, rel_in)):
        print(f'(salta {rel_out}: falta {rel_in})')
        continue
    exportar(rel_in, rel_out, lado)
    if canal:
        emisiva = rel_out.replace('.png', '-emissive.png')
        subprocess.run([sys.executable, os.path.join(RAIZ, 'tools', 'extract-emissive.py'),
                        os.path.join(RAIZ, rel_in), os.path.join(RAIZ, emisiva),
                        canal, str(lado), str(umbral)], check=True)

# fondo principal: recorte/ajuste a 2048x1280 (cover, sin deformar)
rel_in, rel_out, (fw, fh) = FONDO
if os.path.exists(os.path.join(RAIZ, rel_in)):
    img = Image.open(os.path.join(RAIZ, rel_in)).convert('RGB')
    escala = max(fw / img.width, fh / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    x0 = (img.width - fw) // 2
    y0 = (img.height - fh) // 2
    img.crop((x0, y0, x0 + fw, y0 + fh)).save(os.path.join(RAIZ, rel_out), optimize=True)
    print(f'{rel_out}  {fw}x{fh}  {os.path.getsize(os.path.join(RAIZ, rel_out)) // 1024} KB')
