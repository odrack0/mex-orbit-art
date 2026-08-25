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
    ('source/renders/station-cut.png', 'exports/station.png', 1024, 'c', 16),
]


def exportar(rel_in, rel_out, lado):
    img = Image.open(os.path.join(RAIZ, rel_in)).convert('RGBA')
    img = img.resize((lado, lado), Image.LANCZOS)
    destino = os.path.join(RAIZ, rel_out)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    img.save(destino, optimize=True)
    print(f'{rel_out}  {lado}px  {os.path.getsize(destino) // 1024} KB')


for rel_in, rel_out, lado, canal, umbral in PIEZAS:
    exportar(rel_in, rel_out, lado)
    if canal:
        emisiva = rel_out.replace('.png', '-emissive.png')
        subprocess.run([sys.executable, os.path.join(RAIZ, 'tools', 'extract-emissive.py'),
                        os.path.join(RAIZ, rel_in), os.path.join(RAIZ, emisiva),
                        canal, str(lado), str(umbral)], check=True)
