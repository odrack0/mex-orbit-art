# -*- coding: utf-8 -*-
"""Normaliza un modelo crudo de Meshy al contrato de MexOrbit y lo exporta listo
para el cliente.

Meshy devuelve el modelo DE PIE (interpreta la imagen como un poster: el largo
del bicho queda en Z) y sin presupuesto: 2 M de triangulos y texturas de 2048
para algo que se dibuja a 178 px. Este script hace las cinco cosas que lo
convierten en asset:

  1. TUMBARLO  -90 en X. El largo pasa a +Y, que al exportar a glTF es -Z, que
     es el "adelante" de Godot. La proa acaba mirando donde debe sin tocar nada
     mas.
  2. PIVOTE    al centro de la caja. Descentrado, la nave orbita en vez de virar.
  3. DECIMAR   a un presupuesto. Medido: 15 000 tris son indistinguibles de los
     dos millones a tamanio de juego, porque el detalle vive en el mapa de
     normales, no en los poligonos.
  4. TEXTURAS  a 512. Tres mapas de 2048 son 48 MB de VRAM para un bicho cuyo
     atlas entero cuesta 11,7.
  5. EMISION   Meshy pinta las vetas y los nucleos en el ALBEDO y deja
     Emission Strength en 0, o sea que no brillan. Se saca por dominancia de
     canal —la misma heuristica que extract-emissive.py— pero UNA vez, horneada
     en su propia textura, en vez de adivinarla en cada render.

Uso:
  blender --background --factory-startup --python normalize-model.py -- \
      <entrada.glb> <salida.glb> [tris] [lado_textura] [canal r|g|b] [ganancia]
"""
import bpy, sys, os, math, mathutils
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
TRIS = int(argv[2]) if len(argv) > 2 else 15000
LADO = int(argv[3]) if len(argv) > 3 else 512
CANAL = (argv[4] if len(argv) > 4 else "r").lower()
GANANCIA = float(argv[5] if len(argv) > 5 else 1.0)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
obj = [o for o in bpy.data.objects if o.type == "MESH"][0]
obj.name = os.path.splitext(os.path.basename(salida))[0]

tris0 = sum(len(p.vertices) - 2 for p in obj.data.polygons)

def caja():
    co = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return co.min(axis=0), co.max(axis=0)

# ---- 1. tumbar, SOLO si hace falta ----
# Meshy devuelve el modelo de pie, con el largo en Z. Pero este script tambien se
# corre sobre su propia salida (el master de trabajo -> el asset de juego), y ahi
# el modelo ya viene tumbado: rotar a ciegas lo pondria de pie otra vez. La
# senial es la caja — en un juego cenital el alto es la dimension MENOR, asi que
# si Z es la mayor es que sigue de pie.
#
# Se transforma la MALLA, no el objeto: transform_apply es un operador y su poll
# falla en silencio con --background, dejando la rotacion sin aplicar.
mini, maxi = caja()
ext = maxi - mini
if ext[2] >= max(ext[0], ext[1]):
    obj.data.transform(mathutils.Matrix.Rotation(math.radians(-90), 4, "X"))
    obj.data.update()
    print("TUMBADO  -90 en X (entraba de pie: alto era la dimension mayor)")
else:
    print("TUMBADO  no hacia falta, ya venia en el plano")

# ---- 2. pivote al centro ----
mini, maxi = caja()
centro = (mini + maxi) * 0.5
obj.data.transform(mathutils.Matrix.Translation(Vector(-centro)))
obj.data.update()
dim = maxi - mini
print("CAJA  ancho %.3f  largo %.3f  alto %.3f   (alto/largo = %.0f%%)"
      % (dim[0], dim[1], dim[2], 100.0 * dim[2] / dim[1]))

# ---- 3. decimar ----
if TRIS and tris0 > TRIS:
    mod = obj.modifiers.new("dec", "DECIMATE")
    mod.ratio = TRIS / float(tris0)

# ---- 4. texturas ----
for img in bpy.data.images:
    if img.size[0] > LADO:
        img.scale(LADO, LADO)

# ---- 5. emision ----
mat = bpy.data.materials[0]
mat.name = obj.name
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")

# La textura de albedo se busca SIGUIENDO EL ENLACE de Base Color, no por su
# nombre: el exportador de glTF renombra las imagenes al escribir, asi que
# buscar "base" funciona con el crudo de Meshy y falla en cuanto el script se
# corre sobre su propia salida — que es justo el caso del master de trabajo.
enlaces_base = bsdf.inputs["Base Color"].links
base = enlaces_base[0].from_node if enlaces_base else None
if base is None or base.type != "TEX_IMAGE":
    print("AVISO: Base Color sin textura; no se puede derivar la emision")

# Si ya viene con emision (el modelo pasó por aqui antes), no se vuelve a
# derivar: aplicarla dos veces la duplicaria sobre si misma.
ya_emite = bool(bsdf.inputs["Emission Color"].links)
if ya_emite:
    print("EMISION ya presente: se respeta la del modelo de entrada")

if base is not None and not ya_emite:
    LADO_REAL = base.image.size[0]
    px = np.empty(LADO_REAL * LADO_REAL * 4, dtype=np.float32)
    base.image.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    idx = {"r": 0, "g": 1, "b": 2}[CANAL]
    otros = [i for i in (0, 1, 2) if i != idx]
    mask = np.clip(px[:, idx] - np.maximum(px[:, otros[0]], px[:, otros[1]]), 0.0, 1.0)
    cobertura = float((mask > 0.02).mean())

    emi = np.zeros_like(px)
    emi[:, :3] = px[:, :3] * (mask * GANANCIA)[:, None]
    emi[:, 3] = 1.0
    img_emi = bpy.data.images.new("emissive", LADO_REAL, LADO_REAL, alpha=True)
    img_emi.pixels.foreach_set(emi.reshape(-1))
    img_emi.pack()

    nodo_emi = nt.nodes.new("ShaderNodeTexImage")
    nodo_emi.image = img_emi
    nodo_emi.image.colorspace_settings.name = "sRGB"
    nodo_emi.location = (-400, -300)
    nt.links.new(nodo_emi.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    print("EMISION canal '%s': %.1f%% de la textura emite" % (CANAL, cobertura * 100))

# ---- exportar ----
os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=True,
                          export_yup=True, use_selection=False)

dg = bpy.context.evaluated_depsgraph_get()
tris1 = sum(len(p.vertices) - 2 for p in obj.evaluated_get(dg).to_mesh().polygons)
mb0 = os.path.getsize(entrada) / 1048576.0
mb1 = os.path.getsize(salida) / 1048576.0
vram = 3 * LADO * LADO * 4 / 1048576.0
print("TRIS   %d -> %d" % (tris0, tris1))
print("PESO   %.1f MB -> %.1f MB" % (mb0, mb1))
print("VRAM   ~%.1f MB en texturas (3 mapas de %d)" % (vram, LADO))
print("SALIDA %s" % salida)
