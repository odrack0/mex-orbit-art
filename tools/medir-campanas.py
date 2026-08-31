# -*- coding: utf-8 -*-
"""Campanas de popa en 3D: agrupa los vertices de la banda trasera en el plano
X-Z y reporta centro, punto mas trasero y ancho de cada campana. Para una popa
en ANILLO, donde la silueta cenital solo ve la fila de abajo."""
import bpy, sys
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
FRAC_POPA = float(argv[1]) if len(argv) > 1 else 0.10

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
obj = next(o for o in bpy.data.objects if o.type == "MESH")
n = len(obj.data.vertices)
co = np.empty(n * 3, dtype=np.float32)
obj.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3).astype(np.float64)
lo, hi = co.min(axis=0), co.max(axis=0)
largo = hi[1] - lo[1]
umbral = lo[1] + FRAC_POPA * largo
banda = co[co[:, 1] < umbral]
print("POPA Y < %.3f: %d verts" % (umbral, len(banda)))

# Agrupacion por rejilla + union de celdas vecinas ocupadas (la malla viene
# partida por UV, la conectividad no sirve; la cercania espacial si).
CELDA = 0.04
claves = {}
for i, v in enumerate(banda):
    k = (int(np.floor(v[0] / CELDA)), int(np.floor(v[2] / CELDA)))
    claves.setdefault(k, []).append(i)

grupos = []
vistos = set()
for k in claves:
    if k in vistos:
        continue
    cola = [k]
    vistos.add(k)
    miembros = []
    while cola:
        c = cola.pop()
        miembros.extend(claves[c])
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                v2 = (c[0] + dx, c[1] + dz)
                if v2 in claves and v2 not in vistos:
                    vistos.add(v2)
                    cola.append(v2)
    grupos.append(np.array(miembros))

grupos = [g for g in grupos if len(g) >= 40]

# Un grupo mas ancho que una campana son DOS campanas pegadas: se parte por el
# signo de X (los pares del anillo son simetricos respecto al eje).
bocas = []
for g in grupos:
    p = banda[g]
    ancho_x = np.percentile(p[:, 0], 97) - np.percentile(p[:, 0], 3)
    mitades = [p] if ancho_x < 0.2 else [p[p[:, 0] < p[:, 0].mean()], p[p[:, 0] >= p[:, 0].mean()]]
    for m in mitades:
        if len(m) < 15:
            continue
        bocas.append(m)

print("%d bocas:" % len(bocas))
for m in sorted(bocas, key=lambda m: (round(m[:, 2].mean(), 1), m[:, 0].mean())):
    cx, cz = m[:, 0].mean(), m[:, 2].mean()
    ax = np.percentile(m[:, 0], 97) - np.percentile(m[:, 0], 3)
    az = np.percentile(m[:, 2], 97) - np.percentile(m[:, 2], 3)
    print("  x %+0.3f  z %+0.3f  y_tras %.3f  ancho %.3f  verts %d"
          % (cx, cz, m[:, 1].min(), max(ax, az), len(m)))
