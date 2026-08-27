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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salvaguarda import comprobar_salida    # noqa: E402
comprobar_salida(entrada, salida)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)

# TODAS las mallas, no la primera. Con la opcion "Dividir" de Meshy el modelo
# llega ya partido en piezas —que es justo lo que hace falta para animar por
# rotacion en vez de por clave de forma— y quedarse con `[0]` perderia las alas
# en silencio, sin un solo error.
objs = [o for o in bpy.data.objects if o.type == "MESH"]
if not objs:
    print("ERROR: el archivo no trae ninguna malla")
    sys.exit(1)
base_nombre = os.path.splitext(os.path.basename(salida))[0]
if len(objs) == 1:
    objs[0].name = base_nombre
print("PIEZAS %d: %s" % (len(objs), ", ".join(o.name for o in objs)))

def coords(o):
    co = np.empty(len(o.data.vertices) * 3, dtype=np.float32)
    o.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)

def caja():
    """Caja de TODAS las piezas juntas. Cada una por su cuenta daria una caja
    distinta, y entonces el tumbado y el centrado desmontarian el conjunto."""
    lo = np.array([np.inf] * 3, dtype=np.float64)
    hi = np.array([-np.inf] * 3, dtype=np.float64)
    for o in objs:
        c = coords(o)
        lo = np.minimum(lo, c.min(axis=0))
        hi = np.maximum(hi, c.max(axis=0))
    return lo, hi

def tris_de(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)

tris_pieza = [tris_de(o) for o in objs]
tris0 = sum(tris_pieza)

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
# La senial es cual es la dimension MENOR, no cual es la mayor. El grosor del
# bicho es su eje fino, y tras normalizar ese eje tiene que ser Z (el alto).
#
# La primera version preguntaba si Z era la MAYOR, y funcionaba de casualidad
# mientras el bicho fuese mas largo que ancho. Con el Vexor de alas abiertas
# —1,91 de ancho contra 1,61 de largo— dejo de serlo, y el modelo entro de pie
# diciendo "no hacia falta".
fino = int(np.argmin(ext))
if fino == 0:
    print("AVISO: el eje fino es X. Este script solo sabe tumbar desde Y; revisalo a mano")
if fino == 1:
    # La MISMA rotacion a todas las piezas: si cada una girase por su cuenta el
    # conjunto se desmontaria.
    R = mathutils.Matrix.Rotation(math.radians(-90), 4, "X")
    for o in objs:
        o.data.transform(R)
        o.data.update()
    print("TUMBADO  -90 en X (entraba de pie: el eje fino era Y, %.3f)" % ext[1])
else:
    print("TUMBADO  no hacia falta, ya venia en el plano")

# ---- 2. pivote al centro DEL CONJUNTO ----
# El mismo desplazamiento para todas: centrar cada pieza en su propia caja las
# amontonaria en el origen. El pivote de cada ala en su bisagra es otra decision
# y vive en la herramienta de animacion, no aqui — aqui solo se centra el bicho.
mini, maxi = caja()
centro = (mini + maxi) * 0.5
Tr = mathutils.Matrix.Translation(Vector(-centro))
for o in objs:
    o.data.transform(Tr)
    o.data.update()
dim = maxi - mini
print("CAJA  ancho %.3f  largo %.3f  alto %.3f   (alto/largo = %.0f%%)"
      % (dim[0], dim[1], dim[2], 100.0 * dim[2] / dim[1]))

if len(objs) > 1:
    for o in objs:
        c = coords(o)
        lo, hi = c.min(axis=0), c.max(axis=0)
        ctr = (lo + hi) * 0.5
        print("      %-18s tris %-7d  centro (%+.3f, %+.3f, %+.3f)  dim (%.2f, %.2f, %.2f)"
              % (o.name[:18], tris_de(o), ctr[0], ctr[1], ctr[2],
                 hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))

# ---- 3. decimar, REPARTIENDO el presupuesto ----
# Un ratio unico por pieza dejaria a un ala de 2 000 triangulos igual de densa
# que un cuerpo de 200 000. El presupuesto se reparte en proporcion a lo que
# cada pieza traia, asi que todas bajan al mismo ritmo.
if TRIS and tris0 > TRIS:
    ratio = TRIS / float(tris0)
    for o in objs:
        mod = o.modifiers.new("dec", "DECIMATE")
        mod.ratio = ratio

# ---- 4. texturas ----
for img in bpy.data.images:
    if img.size[0] > LADO:
        img.scale(LADO, LADO)

# ---- 5. emision, material por material ----
# Con el modelo partido puede venir un material por pieza. Cada uno necesita su
# emision, pero si comparten la MISMA textura de albedo la mascara se calcula una
# sola vez: derivarla por material duplicaria la imagen en el GLB.
usados = []
for o in objs:
    for m in o.data.materials:
        if m is not None and m not in usados:
            usados.append(m)
if not usados:
    usados = list(bpy.data.materials)

print("MATERIALES %d en %d piezas" % (len(usados), len(objs)))
if len(usados) > 1:
    print("      AVISO: un material por pieza son varias draw calls por bicho.")
    print("      Con 150 instancias eso se nota; lo ideal es un solo material y")
    print("      un solo atlas para todo el modelo.")

cache_emi = {}      # imagen de albedo -> imagen emisiva derivada

for mat in usados:
    if not mat.use_nodes:
        continue
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        continue

    # La textura de albedo se busca SIGUIENDO EL ENLACE de Base Color, no por su
    # nombre: el exportador de glTF renombra las imagenes al escribir, asi que
    # buscar "base" funciona con el crudo de Meshy y falla en cuanto el script se
    # corre sobre su propia salida — que es justo el caso del master de trabajo.
    enlaces_base = bsdf.inputs["Base Color"].links
    base = enlaces_base[0].from_node if enlaces_base else None
    if base is None or base.type != "TEX_IMAGE":
        print("AVISO  '%s': Base Color sin textura, sin emision que derivar" % mat.name)
        continue

    # Si ya viene con emision (el modelo paso por aqui antes), no se vuelve a
    # derivar: aplicarla dos veces la duplicaria sobre si misma.
    if bsdf.inputs["Emission Color"].links:
        print("EMISION '%s' ya presente: se respeta la del modelo de entrada" % mat.name)
        continue

    if base.image in cache_emi:
        img_emi = cache_emi[base.image]
    else:
        LADO_REAL = base.image.size[0]
        px = np.empty(LADO_REAL * LADO_REAL * 4, dtype=np.float32)
        base.image.pixels.foreach_get(px)
        px = px.reshape(-1, 4)
        idx = {"r": 0, "g": 1, "b": 2}[CANAL]
        otros = [i for i in (0, 1, 2) if i != idx]
        mask = np.clip(px[:, idx] - np.maximum(px[:, otros[0]], px[:, otros[1]]), 0.0, 1.0)

        emi = np.zeros_like(px)
        emi[:, :3] = px[:, :3] * (mask * GANANCIA)[:, None]
        emi[:, 3] = 1.0
        img_emi = bpy.data.images.new("emissive_%s" % mat.name, LADO_REAL, LADO_REAL, alpha=True)
        img_emi.pixels.foreach_set(emi.reshape(-1))
        img_emi.pack()
        cache_emi[base.image] = img_emi
        print("EMISION '%s' canal '%s': %.1f%% de la textura emite"
              % (mat.name, CANAL, float((mask > 0.02).mean()) * 100))

    nodo_emi = nt.nodes.new("ShaderNodeTexImage")
    nodo_emi.image = img_emi
    nodo_emi.image.colorspace_settings.name = "sRGB"
    nodo_emi.location = (-400, -300)
    nt.links.new(nodo_emi.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0

# ---- exportar ----
os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
# export_tangents: sin ellas Godot se las inventa al importar, y sobre una malla
# de cientos de cascaras con las UV troceadas las inventa mal — el mapa de
# normales acaba pintando un aspecto de cristal roto que en Blender no se ve,
# porque alli las tangentes se calculan al vuelo y de otra manera.
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=True,
                          export_yup=True, use_selection=False, export_tangents=True)

dg = bpy.context.evaluated_depsgraph_get()
tris1 = 0
for o in objs:
    tris1 += sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).to_mesh().polygons)
mb0 = os.path.getsize(entrada) / 1048576.0
mb1 = os.path.getsize(salida) / 1048576.0
vram = 3 * LADO * LADO * 4 / 1048576.0
print("TRIS   %d -> %d" % (tris0, tris1))
print("PESO   %.1f MB -> %.1f MB" % (mb0, mb1))
print("VRAM   ~%.1f MB en texturas (3 mapas de %d)" % (vram, LADO))
print("SALIDA %s" % salida)
