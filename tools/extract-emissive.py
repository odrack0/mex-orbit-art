# -*- coding: utf-8 -*-
"""Extrae la capa emisiva de un render: los pixeles donde un canal DOMINA
(el nucleo y las venas del Vex = rojez alta). La capa se dibuja en el juego
con blend aditivo y alpha pulsante — glow animado sin perder calidad.

Uso:  py -3 tools/extract-emissive.py <entrada.png> <salida.png> <canal r|g|b> [tam] [umbral]
Ej.:  py -3 tools/extract-emissive.py source/renders/vex-cut.png exports/vex-emissive.png r 256 18
"""
import os
import sys

from PIL import Image, ImageFilter

entrada, salida, canal = sys.argv[1], sys.argv[2], sys.argv[3]
lado = int(sys.argv[4]) if len(sys.argv) > 4 else 256
umbral = int(sys.argv[5]) if len(sys.argv) > 5 else 18

img = Image.open(entrada).convert('RGBA')
px = img.load()
w, h = img.size
sal = Image.new('RGBA', (w, h), (0, 0, 0, 0))
sp = sal.load()
idx = {'r': 0, 'g': 1, 'b': 2}[canal]

for y in range(h):
    for x in range(w):
        r, g, b, a = px[x, y]
        if a < 40:
            continue
        canales = [r, g, b]
        dominante = canales[idx]
        resto = max(c for i, c in enumerate(canales) if i != idx)
        exceso = dominante - resto
        if exceso <= umbral:
            continue
        # el alpha de la capa = cuanto domina el canal; el color conserva el tinte real
        fuerza = min(255, int((exceso - umbral) * 2.2))
        sp[x, y] = (r, g, b, fuerza)

# pluma sutil para que el glow respire sin bordes duros
sal = sal.filter(ImageFilter.GaussianBlur(1.2))
sal = sal.resize((lado, lado), Image.LANCZOS)
os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
sal.save(salida, optimize=True)
print(f'{salida}  {lado}px  {os.path.getsize(salida) // 1024} KB')
