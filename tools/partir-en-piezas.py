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
# Segmentos de cola. 0 = el cuerpo queda de una pieza.
#
# El abdomen del Vexor es SEGMENTADO —lo dice su propio JSON: "la quitina de
# arriba no se menea; el abdomen segmentado si"— asi que una cadena de trozos no
# es una aproximacion de la ondulacion, es lo que el bicho tiene. Se encadenan
# padre-hijo, de modo que rotar el primero arrastra a los de detras y una onda
# recorre la cola sola.
COLA_SEG = int(argv[4]) if len(argv) > 4 else 0
# Desde donde empieza la cola, en tanto por uno del largo contado DESDE LA POPA.
# 0.32 sale del `from: 0.68` de undulate, medido en su dia sobre el sprite.
COLA_DESDE = float(argv[5]) if len(argv) > 5 else 0.32

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
ys_todo = np.array([v.co.y for v in bm.verts])
y_popa, y_proa = float(ys_todo.min()), float(ys_todo.max())
largo = y_proa - y_popa
y_cola = y_popa + COLA_DESDE * largo

# 0 cuerpo, -1 izq, +1 der, 10+k segmento k de cola
destino = np.zeros(len(bm.verts), dtype=np.int8)
for g in trozos:
    xs = np.array([v.co.x for v in g])
    ys = np.array([v.co.y for v in g])
    cx = 0.5 * (float(xs.min()) + float(xs.max()))
    cy = 0.5 * (float(ys.min()) + float(ys.max()))
    if abs(cx) > CORTE:
        d = 1 if cx > 0 else -1
    elif COLA_SEG > 0 and cy < y_cola:
        # el trozo entero cae en la banda de su centro: nada se corta
        k = int((cy - y_popa) / max(1e-6, (y_cola - y_popa)) * COLA_SEG)
        d = 10 + min(COLA_SEG - 1, max(0, k))
    else:
        d = 0
    for v in g:
        destino[v.index] = d
bm.free()

piezas = [("%s_cuerpo" % BASE, 0), ("%s_ala_izq" % BASE, -1), ("%s_ala_der" % BASE, 1)]
if COLA_SEG > 0:
    print("COLA %d segmentos desde y=%+.3f (%.0f%% del largo desde la popa)"
          % (COLA_SEG, y_cola, COLA_DESDE * 100))
    # se nombran de la union hacia la punta: cola_1 cuelga del cuerpo, cola_2 de
    # cola_1... asi rotar uno arrastra a los de detras, que es lo que hace la onda
    for k in range(COLA_SEG - 1, -1, -1):
        piezas.append(("%s_cola_%d" % (BASE, COLA_SEG - k), 10 + k))
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
        if marca >= 10:
            # La bisagra de un segmento de cola es su borde DELANTERO, no su
            # centro: la union con el segmento de delante. Rotar sobre el centro
            # partiria la cola por la mitad en vez de doblarla.
            bisagra = Vector((0.0, float(c[:, 1].max()), 0.0))
        else:
            bisagra = Vector((CORTE * marca, float(0.5 * (c[:, 1].min() + c[:, 1].max())), 0.0))
        me.transform(Matrix.Translation(-bisagra))
        me.update()
        print("  %-18s caras %6d  bisagra (%+.3f, %+.3f, %+.3f)"
              % (nombre, len(me.polygons), bisagra.x, bisagra.y, bisagra.z))
    else:
        bisagra = Vector((0.0, 0.0, 0.0))
        print("  %-18s caras %6d  (en el origen)" % (nombre, len(me.polygons)))
    creadas.append((ob, marca, bisagra))

# ---- jerarquia ----
# Las alas cuelgan del cuerpo. La cola se ENCADENA: cola_1 del cuerpo, cola_2 de
# cola_1... asi rotar un segmento arrastra a los de detras y una onda recorre la
# cola sin que nadie la coordine.
#
# La posicion de cada hijo se calcula A MANO, restando la bisagra del padre. NO
# se usa `matrix_parent_inverse = padre.matrix_world.inverted()`: en --background
# el depsgraph no se evalua, `matrix_world` viene sin actualizar, y con una cadena
# el error se ACUMULA — la cola salia despegada del cuerpo y cada segmento mas
# lejos que el anterior.
cuerpo = next((o for o, m, _ in creadas if m == 0), None)
por_marca = {m: (o, b) for o, m, b in creadas}
if cuerpo is not None:
    for ob, marca, bisagra in creadas:
        if marca == 0:
            continue
        if marca >= 10 and (marca + 1) in por_marca:
            padre, bis_padre = por_marca[marca + 1]   # el de delante en la cadena
        else:
            padre, bis_padre = cuerpo, Vector((0.0, 0.0, 0.0))
        ob.parent = padre
        ob.matrix_parent_inverse = Matrix()           # identidad: no compensamos nada
        ob.location = bisagra - bis_padre             # relativa al padre, medida
        if marca >= 10:
            print("  cadena: %-16s cuelga de %-16s  local (%+.3f, %+.3f, %+.3f)"
                  % (ob.name, padre.name, ob.location.x, ob.location.y, ob.location.z))

bpy.data.objects.remove(orig, do_unlink=True)
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True)
print("SALIDA %s  (%.1f MB, %d piezas)"
      % (salida, os.path.getsize(salida) / 1048576.0, len(creadas)))
