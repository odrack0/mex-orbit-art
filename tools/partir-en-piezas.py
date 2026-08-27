# -*- coding: utf-8 -*-
"""Parte un modelo en cuerpo + alas SIN cortar la malla, para poder animar por
rotacion de nodos en vez de por clave de forma.

La opcion "Dividir" de Meshy promete esto y no sirve: entrega las piezas SIN
textura, y solo se puede texturizar el modelo entero. Se paga dos veces por algo
inservible.

Pero no hace falta, porque Meshy no entrega una cascara limpia: entrega cientos
de trozos solapados (431 en la primera version del Vexor, 1340 en la de alas
abiertas). Eso, que parece un defecto, es la salida: cada trozo se asigna ENTERO
a un lado o a otro segun donde caiga su centro. Nada se corta, asi que no hay
agujeros ni interiores huecos, y las UV y la textura sobreviven intactas.

Medido en el Vexor de alas abiertas: con el corte en |x| = 0,30 solo el 3,2% de
los trozos quedan a caballo del limite (6,7% de los vertices), y el reparto sale
simetrico — cuerpo 57%, alas 22% y 21%. Con el corte mas afuera empeora: a 0,40
ya cruza el 9,7%.

**El origen de cada ala se coloca EN SU BISAGRA**, no en su centro: rotar sobre
el centro haria que el ala orbitase en vez de abrirse. Es la misma regla del
pivote del contrato, aplicada por pieza.

Uso:
  blender --background --factory-startup --python tools/partir-en-piezas.py -- \\
      <entrada.glb> <salida.glb> [corte] [nombre_base]
"""
import bpy
import bmesh
import os
import sys

import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
CORTE = float(argv[2]) if len(argv) > 2 else 0.30
BASE = argv[3] if len(argv) > 3 else "vexor"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
orig = [o for o in bpy.data.objects if o.type == "MESH"][0]
mat = orig.data.materials[0] if orig.data.materials else None

# Misma senial que el normalizador: el eje fino tiene que ser Z.
co = np.empty(len(orig.data.vertices) * 3, dtype=np.float32)
orig.data.vertices.foreach_get("co", co)
ext = co.reshape(-1, 3).max(axis=0) - co.reshape(-1, 3).min(axis=0)
if int(np.argmin(ext)) == 1:
    orig.data.transform(Matrix.Rotation(np.radians(-90), 4, "X"))
    orig.data.update()

bm = bmesh.new()
bm.from_mesh(orig.data)
bm.verts.ensure_lookup_table()

visto = set()
trozos = []
for v in bm.verts:
    if v.index in visto:
        continue
    pila, grupo = [v], []
    visto.add(v.index)
    while pila:
        u = pila.pop()
        grupo.append(u)
        for e in u.link_edges:
            w = e.other_vert(u)
            if w.index not in visto:
                visto.add(w.index)
                pila.append(w)
    trozos.append(grupo)
print("TROZOS %d  corte |x| = %.2f" % (len(trozos), CORTE))

# Cada VERTICE hereda el destino de su trozo: asi el trozo viaja entero y no se
# parte ninguna cara.
destino = np.zeros(len(bm.verts), dtype=np.int8)   # 0 cuerpo, -1 izq, +1 der
for g in trozos:
    xs = np.array([v.co.x for v in g])
    ctr = 0.5 * (float(xs.min()) + float(xs.max()))
    d = 0 if abs(ctr) <= CORTE else (1 if ctr > 0 else -1)
    for v in g:
        destino[v.index] = d
bm.free()

piezas = [("%s_cuerpo" % BASE, 0), ("%s_ala_izq" % BASE, -1), ("%s_ala_der" % BASE, 1)]
creadas = []
for nombre, marca in piezas:
    bm = bmesh.new()
    bm.from_mesh(orig.data)
    bm.verts.ensure_lookup_table()
    fuera = [f for f in bm.faces
             if destino[f.verts[0].index] != marca]
    bmesh.ops.delete(bm, geom=fuera, context="FACES")
    if not bm.faces:
        bm.free()
        print("AVISO: %s se queda vacia" % nombre)
        continue

    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    if mat is not None:
        me.materials.append(mat)     # UN material para las tres: una draw call

    ob = bpy.data.objects.new(nombre, me)
    bpy.context.scene.collection.objects.link(ob)

    # ---- el origen, EN LA BISAGRA ----
    # El cuerpo se queda en el origen del mundo. Cada ala mueve su malla para que
    # su origen caiga sobre la linea de bisagra: asi rotar el nodo abre el ala en
    # vez de pasearla.
    if marca != 0:
        c = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", c)
        c = c.reshape(-1, 3)
        bisagra = Vector((CORTE * marca, float(0.5 * (c[:, 1].min() + c[:, 1].max())), 0.0))
        me.transform(Matrix.Translation(-bisagra))
        me.update()
        ob.location = bisagra
        print("  %-16s caras %6d  bisagra (%+.3f, %+.3f, %+.3f)"
              % (nombre, len(me.polygons), bisagra.x, bisagra.y, bisagra.z))
    else:
        print("  %-16s caras %6d  (en el origen)" % (nombre, len(me.polygons)))
    creadas.append((ob, marca))

# ---- jerarquia: las alas cuelgan del cuerpo ----
cuerpo = next((o for o, m in creadas if m == 0), None)
if cuerpo is not None:
    for ob, marca in creadas:
        if marca != 0:
            ob.parent = cuerpo
            ob.matrix_parent_inverse = cuerpo.matrix_world.inverted()

bpy.data.objects.remove(orig, do_unlink=True)
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True)
print("SALIDA %s  (%.1f MB, %d piezas)"
      % (salida, os.path.getsize(salida) / 1048576.0, len(creadas)))
