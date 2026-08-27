# -*- coding: utf-8 -*-
"""Anima las alas por ROTACION DE NODOS, sobre un modelo ya partido en piezas.

Sustituye a `animar-alas.py`, que lo hacia con una clave de forma. La clave de
forma funcionaba, pero se midio lo que cuesta: con 150 instancias, el mero hecho
de que la malla tenga morph target baja de 190 a 113 fps SIN reproducir nada. Un
nodo rotado es una matriz; una clave de forma son deltas por vertice.

Y ademas el nodo gira en ARCO. La clave de forma interpola en linea recta, asi
que la punta del ala viaja por la cuerda: a 42 grados apenas se nota, a 110 el
ala atravesaria el cuerpo. Con nodos el angulo no tiene techo.

Entra un GLB de `partir-en-piezas.py`, que ya trae el origen de cada ala EN SU
BISAGRA. Rotar sobre el centro del ala la haria orbitar en vez de abrirse.

**El sentido importa: de ABIERTAS a plegadas.** La pose de reposo del modelo es la
extendida —es la unica que Meshy puede dar, y la unica desde la que se puede
animar— asi que la animacion cierra y vuelve a abrir, nunca al reves.

  blender --background --factory-startup --python animar-nodos.py -- \\
      <entrada.glb> <salida.glb> [grados] [ciclos] [fotogramas] [fps]
"""
import bpy
import math
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
GRADOS = float(argv[2]) if len(argv) > 2 else 60.0
CICLOS = int(argv[3]) if len(argv) > 3 else 1
FOTOGRAMAS = int(argv[4]) if len(argv) > 4 else 26
FPS = int(argv[5]) if len(argv) > 5 else 12

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)

alas = [o for o in bpy.data.objects if o.type == "MESH" and "ala" in o.name.lower()]
if not alas:
    print("ERROR: no hay piezas con 'ala' en el nombre. Pasa antes por partir-en-piezas.py")
    sys.exit(1)
for o in alas:
    # El importador de glTF deja los objetos en modo CUATERNION. Poner keyframes
    # en `rotation_euler` sobre eso deja dos modos conviviendo, el exportador
    # avisa "Multiple rotation mode detected" y tira la animacion entera: el GLB
    # sale sin un solo canal y sin error que lo diga.
    o.rotation_mode = "XYZ"
    print("ALA  %-18s bisagra (%+.3f, %+.3f, %+.3f)  modo %s"
          % (o.name, o.location.x, o.location.y, o.location.z, o.rotation_mode))

esc = bpy.context.scene
esc.frame_start = 1
esc.frame_end = FOTOGRAMAS
# Los mismos 12 fps del atlas. No es cosmetico: la DURACION del GLB es lo que lee
# el AnimationPlayer, y de ahi sale la fase que alimenta el pulso emisivo. A los
# 24 de fabrica el ciclo duraria la mitad y el destello caeria donde no toca.
esc.render.fps = FPS

for f in range(1, FOTOGRAMAS + 1):
    t = float(f - 1) / float(FOTOGRAMAS)
    # 0 = abiertas (la pose del modelo), 1 = plegadas
    pliegue = 0.5 - 0.5 * math.cos(2.0 * math.pi * CICLOS * t)
    for o in alas:
        signo = 1.0 if o.location.x > 0 else -1.0
        o.rotation_euler = (0.0, math.radians(GRADOS) * pliegue * signo, 0.0)
        o.keyframe_insert(data_path="rotation_euler", frame=f)

for o in alas:
    if o.animation_data and o.animation_data.action:
        o.animation_data.action.name = "idle"

print("ANIM %d fotogramas a %d fps = %.2f s, %d ciclo(s), %.0f grados"
      % (FOTOGRAMAS, FPS, FOTOGRAMAS / float(FPS), CICLOS, GRADOS))
print("     el ultimo fotograma repite el primero: el bucle cierra por construccion")

os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
# export_animation_mode="SCENE" y no el modo por acciones de fabrica: cada ala
# tiene su propia Action —el signo del giro es opuesto— y por acciones salian DOS
# animaciones, `idle` e `idle.001`. Godot habria reproducido una y movido un ala
# sola. En modo escena, la linea de tiempo entera es UNA animacion con los dos
# canales dentro.
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True, export_animations=True,
                          export_animation_mode="SCENE", export_frame_range=True)
print("PESO  %.1f MB -> %.1f MB" % (os.path.getsize(entrada) / 1048576.0,
                                    os.path.getsize(salida) / 1048576.0))
print("SALIDA %s" % salida)
