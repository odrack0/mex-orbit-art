# -*- coding: utf-8 -*-
"""Alas que se pliegan, por clave de forma. Blender headless.

Por que clave de forma y no esqueleto: un armature pide modo edicion y pintar
pesos, y los operadores de modo fallan en silencio con --background. Una clave
de forma es dato puro —dos posiciones por vertice—, glTF la exporta como morph
target y Godot la reproduce con AnimationPlayer.

El precio: el vertice viaja en LINEA RECTA entre las dos poses, no en arco. Con
angulos moderados no se nota; a 90 grados el ala atravesaria el cuerpo.

La bisagra y la banda salen de medir la malla, no de estimarlas: en el Vexor el
ancho salta de 0,512 a 1,102 en t=0,75, que es donde acaban las placas del torax
y empiezan las alas.

  blender --background --factory-startup --python animar-alas.py -- \
      <entrada.glb> <salida.glb> [bisagra] [banda] [grados] [ciclos] [fotogramas]
"""
import bpy, sys, os, math
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
BISAGRA = float(argv[2]) if len(argv) > 2 else 0.26
BANDA = float(argv[3]) if len(argv) > 3 else 0.30
GRADOS = float(argv[4]) if len(argv) > 4 else 42.0
CICLOS = int(argv[5]) if len(argv) > 5 else 2
FOTOGRAMAS = int(argv[6]) if len(argv) > 6 else 48

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
obj = [o for o in bpy.data.objects if o.type == "MESH"][0]

n = len(obj.data.vertices)
co = np.empty(n * 3, dtype=np.float32)
obj.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3).astype(np.float64)

# Peso del pliegue: 0 en la bisagra, 1 una banda mas afuera. No es un pliegue
# rigido a proposito — el ala se DOBLA, que es lo que hace una de verdad, y de
# paso no deja arruga dura en la union.
lado = np.sign(co[:, 0])
dist = np.abs(co[:, 0]) - BISAGRA
w = np.clip(dist / BANDA, 0.0, 1.0)
w = w * w * (3.0 - 2.0 * w)          # suavizado, para que arranque sin canto

plegado = co.copy()
ang = np.radians(GRADOS) * w * lado   # las dos alas suben: espejo en el signo
dx = np.abs(co[:, 0]) - BISAGRA
dz = co[:, 2]
c, s = np.cos(ang), np.sin(ang)
plegado[:, 0] = lado * (BISAGRA + dx * c - dz * s)
plegado[:, 2] = dx * s + dz * c

movidos = int((w > 0.01).sum())
print("ALAS  bisagra |x|=%.2f  banda %.2f  %.0f grados" % (BISAGRA, BANDA, GRADOS))
print("      %d de %d vertices se mueven (%.1f%%)" % (movidos, n, 100.0 * movidos / n))
print("      desplazamiento maximo %.3f" % float(np.abs(plegado - co).max()))

base = obj.shape_key_add(name="Basis", from_mix=False)
llave = obj.shape_key_add(name="alas_plegadas", from_mix=False)
llave.data.foreach_set("co", plegado.astype(np.float32).reshape(-1))
llave.value = 0.0

# 0 -> 1 -> 0 por ciclo. El ultimo fotograma repite el primero, asi que el bucle
# cierra POR CONSTRUCCION: no hay costura que medir ni valle que buscar, que es
# justo la maquinaria que se cae al dejar de pedir el movimiento a un video.
esc = bpy.context.scene
esc.frame_start = 1
esc.frame_end = FOTOGRAMAS
llaves = obj.data.shape_keys
llaves.animation_data_create()
for f in range(1, FOTOGRAMAS + 1):
    t = float(f - 1) / float(FOTOGRAMAS)
    llave.value = 0.5 - 0.5 * math.cos(2.0 * math.pi * CICLOS * t)
    llave.keyframe_insert(data_path="value", frame=f)
if llaves.animation_data.action:
    llaves.animation_data.action.name = "idle"
print("ANIM  %d fotogramas, %d ciclos, cierra por construccion" % (FOTOGRAMAS, CICLOS))

bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True, export_animations=True,
                          export_morph=True, export_frame_range=True)
print("PESO  %.1f MB -> %.1f MB" % (os.path.getsize(entrada) / 1048576.0,
                                    os.path.getsize(salida) / 1048576.0))
print("SALIDA %s" % salida)
