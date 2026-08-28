# -*- coding: utf-8 -*-
"""Hornea el sprite 2D de un modelo 3D: los tres PNG que el cliente ya consume.

Es la salida barata del pipeline de modelo unico. El GLB sirve la calidad alta;
para media y baja —donde `quality.gd` dice `npc: 0-1 PNG fijo`— se hornea una
imagen desde el MISMO modelo. No son dos catalogos: es un asset con dos salidas,
igual que export-png.py saca 512 y 1024 del mismo recorte.

**Tres pases, no uno**, y esto es lo que se pasa por alto: la calidad MEDIA no
dibuja una imagen plana. `entity_node.gd` monta la capa emisiva como un Sprite2D
aparte en blend ADITIVO y le pulsa la intensidad, y monta `relieve.gdshader` con
un mapa de normales para que la luz no gire con el bicho. Un solo render deja a
media sin latido y sin relieve.

  1. BASE      el cuerpo iluminado, con la emision APAGADA. Si se deja encendida,
               las vetas van dos veces: una en el cuerpo y otra en la capa
               aditiva, y el nucleo se sobreexpone hasta blanco.
  2. EMISIVA   solo lo que emite, sin luces y con el mundo negro. Es lo que
               extract-emissive.py adivinaba por dominancia de canal; aqui se
               lee del material.
  3. NORMAL    la normal de superficie en espacio de PANTALLA, que es lo que
               `relieve.gdshader` espera. Sustituye a gen-normal.py, que la
               deducia de la silueta y de la luminancia pasada por alto.

La camara es ortografica y CENITAL, que es el contrato del sprite. Y la luz va
axial —desde la camara— por la misma razon de siempre: el sprite rota en el juego
y una luz lateral giraria con el.

  blender --background --factory-startup --python hornear-sprite.py -- \\
      <modelo.glb> <carpeta_salida> <nombre> [lado]
"""
import bpy
import math
import os
import sys

import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida_dir, nombre = argv[0], argv[1], argv[2]
LADO = int(argv[3]) if len(argv) > 3 else 512

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salvaguarda import comprobar_salida    # noqa: E402
comprobar_salida(entrada, os.path.join(salida_dir, nombre + "-base.png"))
os.makedirs(salida_dir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
mallas = [o for o in bpy.data.objects if o.type == "MESH"]
if not mallas:
    print("ERROR: sin malla")
    sys.exit(1)

# ---- encuadre ----
lo = np.array([np.inf] * 3)
hi = np.array([-np.inf] * 3)
for o in mallas:
    mw = o.matrix_world
    for v in o.data.vertices:
        w = mw @ v.co
        lo = np.minimum(lo, [w.x, w.y, w.z])
        hi = np.maximum(hi, [w.x, w.y, w.z])
centro = Vector(tuple((lo + hi) * 0.5))
# El lado se toma del EJE MAYOR en el plano, no de cada uno: asi el bicho ocupa
# lo mismo en las tres imagenes y las capas casan pixel a pixel.
radio = float(max(hi[0] - lo[0], hi[1] - lo[1])) * 0.5
print("CAJA  %.3f x %.3f x %.3f" % tuple(hi - lo))

diana = bpy.data.objects.new("d", None)
bpy.context.scene.collection.objects.link(diana)
diana.location = centro
cd = bpy.data.cameras.new("c")
cd.type = "ORTHO"
cd.ortho_scale = radio * 2.06       # un pelin de aire, como el margen del atlas
cam = bpy.data.objects.new("c", cd)
bpy.context.scene.collection.objects.link(cam)
cam.location = centro + Vector((0.0, 0.0, radio * 8.0))
cam.rotation_euler = (0.0, 0.0, 0.0)   # cenital puro, mirando -Z
bpy.context.scene.camera = cam

esc = bpy.context.scene
esc.render.engine = "BLENDER_EEVEE"
esc.render.resolution_x = esc.render.resolution_y = LADO
esc.render.film_transparent = True
esc.render.image_settings.file_format = "PNG"
esc.render.image_settings.color_mode = "RGBA"

mundo = bpy.data.worlds.new("w")
mundo.use_nodes = True
bpy.context.scene.world = mundo
fondo = mundo.node_tree.nodes["Background"]


def render(ruta):
    esc.render.filepath = ruta
    bpy.ops.render.render(write_still=True)
    print("  -> %s" % os.path.basename(ruta))


def emisiones(valor):
    """Pone la fuerza de emision de todos los materiales, y devuelve las de antes."""
    previos = {}
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is None:
            continue
        previos[m.name] = b.inputs["Emission Strength"].default_value
        b.inputs["Emission Strength"].default_value = valor
    return previos


# ---- 1. BASE: cuerpo iluminado, emision apagada ----
sol_d = bpy.data.lights.new("sol", type="SUN")
sol_d.energy = 3.2
sol = bpy.data.objects.new("sol", sol_d)
bpy.context.scene.collection.objects.link(sol)
# Luz AXIAL, desde la camara: el sprite rota en el juego y una luz lateral
# giraria con el. Es la regla 3 del contrato de render, y sigue vigente para el
# sprite aunque el modelo ya no la necesite.
sol.rotation_euler = (0.0, 0.0, 0.0)
fondo.inputs[1].default_value = 0.28

previos = emisiones(0.0)
print("BASE (emision apagada para que no vaya dos veces)")
render(os.path.join(salida_dir, nombre + "-base.png"))

# ---- 2. EMISIVA: solo lo que brilla ----
for m in bpy.data.materials:
    if m.use_nodes:
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is not None and m.name in previos:
            b.inputs["Emission Strength"].default_value = previos[m.name]
sol_d.energy = 0.0
fondo.inputs[1].default_value = 0.0
print("EMISIVA (sin luces, mundo negro)")
render(os.path.join(salida_dir, nombre + "-emissive.png"))

# ---- 3. NORMAL en espacio de pantalla ----
# Se sustituye el material por una emision que pinta la normal como color, en vez
# de usar el compositor: menos piezas y funciona igual en headless.
mat_n = bpy.data.materials.new("normal_pass")
mat_n.use_nodes = True
nt = mat_n.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
salida_n = nt.nodes.new("ShaderNodeOutputMaterial")
emi = nt.nodes.new("ShaderNodeEmission")
geo = nt.nodes.new("ShaderNodeNewGeometry")
# La normal se usa TAL CUAL, en espacio de mundo, sin transformar a camara. En un
# sprite CENITAL los dos espacios coinciden —X es X, Y es Y y Z apunta a la
# camara— asi que el nodo de transformacion sobraba y ademas salia mal: el mapa
# se veia amarillo-verde en vez del azulado que espera relieve.gdshader, donde
# una superficie plana de cara a la camara vale (0,5, 0,5, 1,0).
mul = nt.nodes.new("ShaderNodeVectorMath")
mul.operation = "MULTIPLY_ADD"
mul.inputs[1].default_value = (0.5, 0.5, 0.5)
mul.inputs[2].default_value = (0.5, 0.5, 0.5)
nt.links.new(geo.outputs["Normal"], mul.inputs[0])
nt.links.new(mul.outputs[0], emi.inputs["Color"])
nt.links.new(emi.outputs["Emission"], salida_n.inputs["Surface"])

for o in mallas:
    o.data.materials.clear()
    o.data.materials.append(mat_n)

# Sin gestion de color. El pase de normales son DATOS, no una imagen: la curva de
# vista de Blender los deforma y el mapa sale sesgado —medido, 0,65/0,68/0,76 en
# vez de 0,50/0,50/0,91— asi que el shader de relieve leeria normales torcidas.
#
# "Raw" y no "Standard": Standard sigue aplicando la curva sRGB de salida, y un
# 0,5 lineal se escribe como 0,73. Medido: R 0,71 G 0,74 con Standard contra el
# 0,50 que toca. Raw escribe el valor tal cual.
esc.view_settings.view_transform = "Raw"
esc.view_settings.look = "None"
esc.view_settings.exposure = 0.0
esc.view_settings.gamma = 1.0
print("NORMAL (normal de superficie, sin gestion de color)")
render(os.path.join(salida_dir, nombre + "-base-normal.png"))

print("\nHORNEADO %s a %d px" % (nombre, LADO))
print("Al JSON del bicho:  texture -> -base.png · emissive -> -emissive.png · normal -> -base-normal.png")
