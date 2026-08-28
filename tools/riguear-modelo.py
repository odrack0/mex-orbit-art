# -*- coding: utf-8 -*-
"""Pone un esqueleto con pesos a un modelo entero, para que se doble sin romperse.

Sustituye a `partir-en-piezas.py` para todo lo que sea ANIMAR. Partir en piezas
funciona, pero es articulacion rigida: cada vertice pertenece ENTERO a una pieza,
asi que al rotar el ala su borde y el del cuerpo —que en reposo coincidian— se
separan y abren una rendija. Se ve, y no tiene arreglo dentro de ese enfoque.

Con esqueleto un vertice no pertenece a un hueso: PESA entre varios. Uno de la
bisagra puede ser 50% cuerpo y 50% ala, asi que al rotar se mueve a medias y la
superficie SE ESTIRA en vez de romperse. No hay costura porque no hubo corte.

Y sale mas barato de dibujar: una sola malla es una draw call por bicho en vez de
seis. Medido en el banco, por encima de 30 000 triangulos el cuello de botella
deja de ser la geometria y pasa a ser el numero de piezas.

Los pesos NO se pintan a mano: se derivan de la posicion con una transicion suave,
igual que se derivo la emision del color. La bisagra del ala y las bandas de cola
son las mismas que se midieron sobre la malla.

Entra un modelo ENTERO y SOLDADO (de `normalize-model.py`, que suelda desde el
arreglo de las esquirlas). Si entra partido en piezas, no sirve.

  blender --background --factory-startup --python riguear-modelo.py -- \\
      <entrada.glb> <salida.glb> [bisagra] [banda] [cola_desde] [cola_seg]
"""
import bpy
import math
import os
import sys

import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
BISAGRA = float(argv[2]) if len(argv) > 2 else 0.30
BANDA = float(argv[3]) if len(argv) > 3 else 0.22
COLA_DESDE = float(argv[4]) if len(argv) > 4 else 0.32
COLA_SEG = int(argv[5]) if len(argv) > 5 else 3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salvaguarda import comprobar_salida    # noqa: E402
comprobar_salida(entrada, salida)


def suave(x):
    """smoothstep: arranca y termina sin canto. Con una rampa lineal la union se
    marca como un pliegue recto, que es justo lo que se viene a evitar."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
mallas = [o for o in bpy.data.objects if o.type == "MESH"]
if len(mallas) != 1:
    print("ERROR: se esperaba UNA malla entera y llegaron %d (%s)."
          % (len(mallas), ", ".join(o.name for o in mallas)))
    print("       El esqueleto va sobre el modelo entero, no sobre uno ya partido.")
    sys.exit(1)
obj = mallas[0]

n = len(obj.data.vertices)
co = np.empty(n * 3, dtype=np.float32)
obj.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3).astype(np.float64)
lo, hi = co.min(axis=0), co.max(axis=0)
print("MALLA %s  %d verts  caja (%.3f, %.3f, %.3f)" % (obj.name, n, *(hi - lo)))

y_popa, y_proa = float(lo[1]), float(hi[1])
largo = y_proa - y_popa
y_cola = y_popa + COLA_DESDE * largo
bordes = [y_cola - (y_cola - y_popa) * k / float(COLA_SEG) for k in range(COLA_SEG + 1)]

# ---- el esqueleto ----
arm = bpy.data.armatures.new("esq")
esq = bpy.data.objects.new("esq", arm)
bpy.context.scene.collection.objects.link(esq)
bpy.context.view_layer.objects.active = esq
bpy.ops.object.mode_set(mode="EDIT")

# Todos los huesos apuntan a +Y (el eje del cuerpo) para que su marco local
# coincida con el del mundo en reposo. Asi el cliente puede rotar por ejes
# predecibles en vez de tener que adivinar el roll de cada hueso.
raiz = arm.edit_bones.new("raiz")
raiz.head, raiz.tail = Vector((0, 0, 0)), Vector((0, largo * 0.25, 0))

y_ala = float(co[np.abs(co[:, 0]) > BISAGRA, 1].mean()) if (np.abs(co[:, 0]) > BISAGRA).any() else 0.0
for nombre, signo in (("ala_izq", -1.0), ("ala_der", 1.0)):
    b = arm.edit_bones.new(nombre)
    b.head = Vector((BISAGRA * signo, y_ala, 0.0))
    b.tail = Vector((BISAGRA * signo, y_ala + largo * 0.2, 0.0))
    b.parent = raiz

previo = raiz
for k in range(COLA_SEG):
    b = arm.edit_bones.new("cola_%d" % (k + 1))
    b.head = Vector((0.0, bordes[k], 0.0))
    b.tail = Vector((0.0, bordes[k] - (bordes[k] - bordes[k + 1]) * 0.9, 0.0))
    b.parent = previo
    previo = b

bpy.ops.object.mode_set(mode="OBJECT")
print("HUESOS %s" % [b.name for b in arm.bones])

# ---- pesos por posicion ----
# El ala: 0 dentro del cuerpo, 1 fuera, con la transicion CENTRADA en la bisagra.
# Esa banda es la que se estira, y es la que hace que no haya costura.
ax = np.abs(co[:, 0])
w_ala = suave((ax - (BISAGRA - BANDA * 0.5)) / BANDA)
w_izq = np.where(co[:, 0] < 0, w_ala, 0.0)
w_der = np.where(co[:, 0] > 0, w_ala, 0.0)

# La cola: una rampa por frontera, y el peso de cada segmento es la diferencia
# entre su rampa y la del siguiente. Asi los pesos suman 1 por construccion.
banda_cola = (y_cola - y_popa) / float(COLA_SEG) * 0.6
rampas = [suave((bordes[k] - co[:, 1]) / max(1e-6, banda_cola)) for k in range(COLA_SEG + 1)]
rampas.append(np.zeros(n))
w_cola = [rampas[k] - rampas[k + 1] for k in range(COLA_SEG)]

w_cuerpo = np.clip(1.0 - w_izq - w_der - rampas[0], 0.0, 1.0)

# La suma por vertice tiene que ser 1. Si algun vertice se queda sin peso, la
# piel lo colapsa al origen del hueso y la malla se aplasta — que es exactamente
# lo que hizo la primera version con la cola.
total = w_cuerpo + w_izq + w_der + sum(w_cola)
print("PESOS  suma por vertice: min %.3f  max %.3f  media %.3f"
      % (total.min(), total.max(), total.mean()))
huerfanos = int((total < 0.5).sum())
if huerfanos:
    print("  AVISO: %d vertices con menos de 0,5 de peso total (%.1f%%) — se van a aplastar"
          % (huerfanos, 100.0 * huerfanos / n))
    # se normaliza: mas vale repartir mal que dejar vertices sueltos
    seguro = np.maximum(total, 1e-6)
    w_cuerpo, w_izq, w_der = w_cuerpo / seguro, w_izq / seguro, w_der / seguro
    w_cola = [w / seguro for w in w_cola]
    print("  normalizado: ahora suman 1 en todos")

grupos = {b.name: obj.vertex_groups.new(name=b.name) for b in arm.bones}
pesos = {"raiz": w_cuerpo, "ala_izq": w_izq, "ala_der": w_der}
for k in range(COLA_SEG):
    pesos["cola_%d" % (k + 1)] = np.clip(w_cola[k], 0.0, 1.0)

for nombre, w in pesos.items():
    idx = np.nonzero(w > 0.001)[0]
    for i in idx:
        grupos[nombre].add([int(i)], float(w[i]), "REPLACE")
    mezcla = int(((w > 0.02) & (w < 0.98)).sum())
    print("  %-10s %6d verts con peso, %5d en la banda que se estira"
          % (nombre, len(idx), mezcla))

mod = obj.modifiers.new("arm", "ARMATURE")
mod.object = esq
obj.parent = esq

bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True, export_skins=True, export_tangents=True)
print("PESO  %.1f MB -> %.1f MB" % (os.path.getsize(entrada) / 1048576.0,
                                    os.path.getsize(salida) / 1048576.0))
print("SALIDA %s" % salida)
