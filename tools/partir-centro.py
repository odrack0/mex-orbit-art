# Parte un prop de UNA malla en dos piezas por RADIO: `centro` (lo que queda
# dentro del corte) y `aro` (lo de fuera), para que el cliente pueda girar una
# sin la otra. Nacio para el portal (1-sep-2026): Meshy lo entrega en una sola
# cascara y el encendido pide que gire el vortice y el anillo se quede quieto.
#
# El corte es por el CENTROIDE de cada triangulo, medido en el plano del disco
# (los dos ejes anchos; el fino es la normal) y como fraccion del radio de la
# huella. Un corte circular sobre un eje de giro es invariante al giro: la
# costura que deja es un circulo que rota sobre si mismo, asi que no se ve.
#
# Donde cortar se MIDE, no se adivina: el histograma radial de triangulos del
# portal (25 cubos) tiene el disco fino entre r 0,12 y 0,56 (~250 tris por
# cubo) y el aro desde 0,56 (salta a 1051 y sigue subiendo). El corte va en el
# ultimo cubo bajo. Con RADIO fuera del valle, una de las dos piezas se lleva
# un pedazo de la otra y el giro lo delata.
#
#   blender --background --factory-startup --python tools/partir-centro.py -- \
#       source/3d-models/portal.glb <cliente>/assets/world/portal.glb 0.56
#
# Las dos piezas comparten material y textura (se copian, no se duplican en el
# GLB: glTF deduplica por referencia). Sale con la misma receta de export que
# normalize-model.py (GLB, Y arriba, tangentes) — es el asset de juego.
import bpy, bmesh, os, sys
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
if len(args) != 3:
    sys.exit("uso: partir-centro.py <entrada.glb> <salida.glb> <radio_frac>")
entrada, salida, RADIO = os.path.abspath(args[0]), os.path.abspath(args[1]), float(args[2])
assert 0.0 < RADIO < 1.0, "radio_frac es una fraccion del radio de la huella (0..1)"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
objs = [o for o in bpy.data.objects if o.type == "MESH"]
if len(objs) != 1:
    sys.exit("RECHAZAR: partir-centro espera UNA malla, hay %d (%s)" % (len(objs), [o.name for o in objs]))
src = objs[0]

# la transformacion se acumula A MANO (Blender headless no evalua el depsgraph)
m = np.array(src.matrix_world)
v = np.array([vt.co[:] for vt in src.data.vertices]) @ m[:3, :3].T + m[:3, 3]
lo, hi = v.min(0), v.max(0)
ext = hi - lo
fino = int(np.argmin(ext))
ejes = [i for i in range(3) if i != fino]
c = (lo + hi) / 2
radio = max(ext[ejes[0]], ext[ejes[1]]) / 2
print("caja %s · eje fino %s · radio de huella %.3f · corte en r=%.2f (%.3f)"
      % (np.round(ext, 3), "XYZ"[fino], radio, RADIO, RADIO * radio))


def pieza(nombre, dentro):
    bm = bmesh.new()
    bm.from_mesh(src.data)
    # coordenadas de mundo sobre la propia malla: la pieza sale con transform identidad
    for vt in bm.verts:
        p = m[:3, :3] @ np.array(vt.co[:]) + m[:3, 3]
        vt.co = p.tolist()
    fuera = []
    for f in bm.faces:
        cen = np.mean([vt.co[:] for vt in f.verts], axis=0)
        r = np.hypot(cen[ejes[0]] - c[ejes[0]], cen[ejes[1]] - c[ejes[1]]) / radio
        if (r < RADIO) != dentro:
            fuera.append(f)
    bmesh.ops.delete(bm, geom=fuera, context="FACES")
    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for mat in src.data.materials:
        me.materials.append(mat)
    o = bpy.data.objects.new(nombre, me)
    bpy.context.scene.collection.objects.link(o)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print("  %-6s %6d tris" % (nombre, tris))
    if tris == 0:
        sys.exit("RECHAZAR: la pieza `%s` salio vacia — el corte %.2f no parte nada" % (nombre, RADIO))
    return o


aro = pieza("aro", False)
centro = pieza("centro", True)
bpy.data.objects.remove(src, do_unlink=True)

os.makedirs(os.path.dirname(salida), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=True,
                          export_yup=True, use_selection=False, export_tangents=True)
print("escrito %s (%.1f MB)" % (salida, os.path.getsize(salida) / 1048576.0))
