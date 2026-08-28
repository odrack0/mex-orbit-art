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
# La luz del horno, tambien por asset. Un bicho de albedo oscuro con vetas sale
# bien con 3,2 y 0,28; una nave METALICA no: un metal sin entorno que reflejar se
# apaga, y el Phoenix salia casi negro al lado de su propio arte 2D. Subir el
# ambiente es darle algo que reflejar.
HORNO_SOL = float(os.environ.get("HORNO_SOL", 3.2))
HORNO_AMBIENTE = float(os.environ.get("HORNO_AMBIENTE", 0.28))

# ABSOLUTA, siempre. Blender resuelve un `render.filepath` RELATIVO contra su
# propia idea de la ruta base, no contra el directorio desde el que se lanza: con
# `exports/horno` como salida el render se fue a un sitio fantasma, el script
# dijo que habia horneado y los PNG del repo se quedaron como estaban. No dio
# ningun error; solo no hizo nada.
salida_dir = os.path.abspath(salida_dir)

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
sol_d.energy = HORNO_SOL
sol = bpy.data.objects.new("sol", sol_d)
bpy.context.scene.collection.objects.link(sol)
# Luz AXIAL, desde la camara: el sprite rota en el juego y una luz lateral
# giraria con el. Es la regla 3 del contrato de render, y sigue vigente para el
# sprite aunque el modelo ya no la necesite.
sol.rotation_euler = (0.0, 0.0, 0.0)
fondo.inputs[1].default_value = HORNO_AMBIENTE

previos = emisiones(0.0)
print("BASE (emision apagada para que no vaya dos veces)")
render(os.path.join(salida_dir, nombre + "-base.png"))

# ---- glow para el pase emisivo ----
# Homologa media con alta. En ALTA el brillo lo hace el `Environment` del
# SubViewport con `glow_enabled`, que DERRAMA lo que pasa de 1 a los pixeles
# vecinos. En MEDIA no hay entorno: hay un PNG. Si el halo no se hornea, media se
# queda con el nucleo recortado —manchones planos reventados— y alta con el rojo
# vivo y halo. Misma luminosidad media, distinto acabado; esto iguala el acabado.
#
# Los tres diales espejan los del cliente (entity_node._construir_malla_3d):
#   umbral 0.9  <- glow_hdr_threshold      fuerza 1.0 <- glow_intensity
#   tamanio     <- no tiene equivalente exacto; se calibro midiendo (ver README)
GLOW_UMBRAL = float(os.environ.get("GLOW_UMBRAL", 0.25))
GLOW_RADIO = float(os.environ.get("GLOW_RADIO", 0.06))   # fraccion del lado
GLOW_FUERZA = float(os.environ.get("GLOW_FUERZA", 1.8))
# El nucleo del horneado sale mas caliente que la emision de ALTA en Godot: al
# mismo pulso, media reventaba el 19,1% de sus pixeles y alta el 8,3%. Homologar
# el acabado es bajar el nucleo A LO QUE DA ALTA y devolver esa energia como halo,
# que es justo lo que hace un bloom: no quema mas, reparte.
GLOW_NUCLEO = float(os.environ.get("GLOW_NUCLEO", 0.09))


def _desenfoque(a, radio):
    """Gauss aproximado por tres cajas seguidas, con sumas acumuladas.

    Tres pasadas de caja convergen a una gaussiana y cuestan O(n) en vez de
    O(n*radio); con 512 px y numpy es instantaneo y no hace falta scipy.
    """
    r = max(1, int(radio))
    for _ in range(3):
        for eje in (0, 1):
            a = np.swapaxes(a, 0, eje)
            pad = np.concatenate([
                np.repeat(a[:1], r + 1, axis=0), a, np.repeat(a[-1:], r, axis=0)], axis=0)
            ac = np.cumsum(pad, axis=0)
            a = (ac[2 * r + 1:] - ac[:-(2 * r + 1)]) / float(2 * r + 1)
            a = np.swapaxes(a, 0, eje)
    return a


def hornear_halo(ruta):
    """Anade a la capa emisiva el halo que en ALTA pone el glow del Environment.

    Homologa el ACABADO, que es lo que quedaba distinto. Con la misma luminosidad
    media, media tenia manchones planos reventados (19,1% de pixeles a tope) y
    alta el rojo vivo con halo (8,7%). El brillo ya casaba; el caracter no.

    Se trabaja sobre el color PREMULTIPLICADO porque es lo que se ve: el cliente
    monta esta capa en blend ADITIVO, donde la aportacion es rgb*a. Sumar el halo
    ahi y recomponer el alfa despues es lo unico que lo deja bien; hacerlo sobre
    el rgb suelto pinta halo donde el alfa lo iba a borrar.
    """
    img = bpy.data.images.load(ruta)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    rgb, alfa = px[:, :, :3], px[:, :, 3:4]

    visible = rgb * alfa
    # El halo sale de la emision ORIGINAL y el nucleo se atenua DESPUES. Al reves
    # —que fue el primer intento— bajar el nucleo dejaba la imagen por debajo del
    # umbral y el halo desaparecia: se medio 12,9% de reventon y ni un pixel de
    # halo fuera de la silueta. Ademas es lo fisico: en ALTA el bloom lee la
    # emision entera, y bajar el nucleo es repartir esa energia, no quitarla.
    altas = np.maximum(visible - GLOW_UMBRAL, 0.0)
    halo = _desenfoque(altas, GLOW_RADIO * min(w, h)) * GLOW_FUERZA
    nueva = visible * GLOW_NUCLEO + halo

    # El alfa tiene que crecer con el halo: cae FUERA de la silueta, donde el
    # render trae alfa 0, y el blend aditivo multiplica por alfa. Sin esto el halo
    # se multiplicaria por cero y no existiria.
    luz = nueva.max(axis=2, keepdims=True)
    na = np.clip(np.maximum(alfa, luz), 0.0, 1.0)
    px[:, :, :3] = np.where(na > 1e-4, nueva / np.maximum(na, 1e-4), 0.0)
    px[:, :, 3:4] = na

    img.pixels = np.clip(px, 0.0, 1.0).ravel().tolist()
    img.filepath_raw = ruta
    img.file_format = "PNG"
    img.save()
    print("  halo: nucleo %.2f umbral %.2f radio %.3f fuerza %.2f -> alfa %.1f%%"
          % (GLOW_NUCLEO, GLOW_UMBRAL, GLOW_RADIO, GLOW_FUERZA, 100.0 * (na > 0.02).mean()))


# ---- 2. EMISIVA: solo lo que brilla, CON el halo de alta ----
for m in bpy.data.materials:
    if m.use_nodes:
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is not None and m.name in previos:
            b.inputs["Emission Strength"].default_value = previos[m.name]
sol_d.energy = 0.0
fondo.inputs[1].default_value = 0.0
print("EMISIVA (sin luces, mundo negro)")
_emi = os.path.join(salida_dir, nombre + "-emissive.png")
render(_emi)
# El halo va SOLO aqui. En el pase de normales seria corrupcion, no brillo, y en
# el base iria dos veces: el cliente ya suma esta capa encima.
hornear_halo(_emi)

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

# ---- anclajes en ESPACIO DE TEXTURA, para el JSON de media y baja ----
# Media no carga el modelo, asi que sus toberas y caniones viven en pixeles de la
# textura. Hasta ahora eran los del arte 2D viejo y no tenian por que caer donde
# el modelo pone las suyas: los caniones del Phoenix estaban a 17 px de su sitio.
# El horno SI conoce la proyeccion que acaba de usar, asi que los convierte el.
marcas = [o for o in bpy.data.objects
          if o.type == "EMPTY" and o.name.startswith(("tobera", "canon"))]
if marcas:
    ppu = LADO / cd.ortho_scale                      # pixeles por unidad de mundo
    # Cuanto hay que escalar la llama para que su PENACHO (el 70% de su textura, y
    # el ciclo de empuje llega a 0,70) mida lo que mide la boca.
    div = 64.0 * 0.70 * 0.70
    mot, can = [], []
    for o in sorted(marcas, key=lambda m: m.location.x):
        x = (o.location.x - centro.x) * ppu
        y = -(o.location.y - centro.y) * ppu          # en la textura, +Y va hacia abajo
        if o.name.startswith("tobera"):
            mot.append('{"x": %.0f, "y": %.0f, "scale": %.3f}'
                       % (x, y, max(o.scale.x, 1e-4) * ppu / div))
        else:
            can.append('{"x": %.0f, "y": %.0f}' % (x, y))
    print("")
    print("Al JSON, anclajes en pixeles de ESTA textura:")
    print('  "engines": [%s],' % ", ".join(mot))
    print('  "cannons": [%s],' % ", ".join(can))
else:
    print("")
    print("(sin marcadores en el GLB: si es una nave, hornea el que salio de")
    print(" marcar-anclajes o los anclajes de media se quedaran a ojo)")

print("\nHORNEADO %s a %d px" % (nombre, LADO))
print("Al JSON del bicho:  texture -> -base.png · emissive -> -emissive.png · normal -> -base-normal.png")
