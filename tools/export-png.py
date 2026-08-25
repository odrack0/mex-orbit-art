# -*- coding: utf-8 -*-
"""Exporta PNGs para el cliente desde los SVG vectorizados (paths M/L/Z).

El cliente consume exportaciones del pipeline, no los SVG fuente (pesan MB y
Godot no necesita re-trazarlos). Requiere matplotlib.

Uso:  py -3 tools/export-png.py
Emite en exports/: phoenix.png (256), vex.png (256), station.png (512)
"""
import os
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIEZAS = [
    ('ships/phoenix.svg', 'exports/phoenix.png', 256),
    ('npcs/vex.svg', 'exports/vex.png', 256),
    ('world/props/station.svg', 'exports/station.png', 512),
]


def parse_d(d):
    verts, codes = [], []
    for sub in d.split('M'):
        sub = sub.strip().rstrip('Zz ').strip()
        if not sub:
            continue
        puntos = [float(p) for p in sub.replace(',', ' ').split()]
        if len(puntos) < 6:
            continue
        xs, ys = puntos[0::2], puntos[1::2]
        verts.append((xs[0], ys[0]))
        codes.append(MPath.MOVETO)
        for x, y in zip(xs[1:], ys[1:]):
            verts.append((x, y))
            codes.append(MPath.LINETO)
        verts.append((xs[0], ys[0]))
        codes.append(MPath.CLOSEPOLY)
    return verts, codes


for rel, destino, lado in PIEZAS:
    with open(os.path.join(RAIZ, rel), encoding='utf-8') as f:
        svg = f.read()
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    w, h = int(m.group(1)), int(m.group(2))
    fig = plt.figure(figsize=(lado / 100, lado / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis('off')
    n = 0
    for match in re.finditer(r'<path([^>]*)/>', svg):
        attrs = match.group(1)
        if 'fill' not in attrs:
            continue
        fill = re.search(r'fill="([^"]+)"', attrs).group(1)
        d = re.search(r'd="([^"]+)"', attrs)
        if not d:
            continue
        verts, codes = parse_d(d.group(1))
        if verts:
            ax.add_patch(PathPatch(MPath(verts, codes), facecolor=fill, edgecolor='none'))
            n += 1
    ruta = os.path.join(RAIZ, destino)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    fig.savefig(ruta, transparent=True)   # fondo transparente: es un sprite
    plt.close(fig)
    print(f'{destino}  {lado}px  {n} paths  {os.path.getsize(ruta) // 1024} KB')
