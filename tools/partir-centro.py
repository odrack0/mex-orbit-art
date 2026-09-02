# Parte un prop de UN objeto en dos piezas por RADIO: `centro` (lo que entra
# por dentro del corte) y `aro` (el resto), para que el cliente pueda girar o
# esconder una sin la otra. Nacio para el portal (1-sep-2026): Meshy lo entrega
# en un solo objeto y el encendido pide que el vortice aparezca y gire y el
# anillo se quede quieto.
#
# Se reparten ISLAS ENTERAS (trozos conectados por aristas), como hace
# partir-en-piezas.py con las alas: una isla va al centro si su vertice mas
# interior queda por debajo de RADIO (fraccion del radio de la huella, medido
# en el plano del disco: los dos ejes anchos; el fino es la normal). Nada se
# corta, asi que no hay costura dentada.
#
# La primera version cortaba por el CENTROIDE de cada triangulo (r 0,56) y
# dejaba el borde interior del aro en dientes de sierra: el disco del vortice
# entra por debajo del anillo hasta r 0,65 con triangulos largos y planos (292
# cruzaban el corte, de r 0,40 a 0,65), y partirlos por la mitad repartia cada
# uno entre las dos piezas. Medido: el objeto son 1018 islas, todas las que
# entran en el disco (rmin < 0,52) son finas (z +0,00..+0,04) y ninguna pasa
# de r 0,66; el aro empieza en r 0,56 (salto x5 en el histograma radial) y
# ninguna isla suya baja de 0,52. Por eso el corte va en 0,52: en el valle,
# lejos de los dos.
#
#   blender --background --factory-startup --python tools/partir-centro.py -- \
#       source/3d-models/portal.glb <cliente>/assets/world/portal.glb 0.52
#
# Las dos piezas comparten material y textura (glTF las referencia, no las
# duplica). Sale con la misma receta de export que normalize-model.py (GLB, Y
# arriba, tangentes) — es el asset de juego.
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
    sys.exit("RECHAZAR: partir-centro espera UN objeto, hay %d (%s)" % (len(objs), [o.name for o in objs]))
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
rv = np.hypot(v[:, ejes[0]] - c[ejes[0]], v[:, ejes[1]] - c[ejes[1]]) / radio
print("caja %s · eje fino %s · radio de huella %.3f · corte en r=%.2f (%.3f)"
      % (np.round(ext, 3), "XYZ"[fino], radio, RADIO, RADIO * radio))

# islas por conectividad de aristas, y a que pieza va cada cara
bm0 = bmesh.new()
bm0.from_mesh(src.data)
bm0.faces.ensure_lookup_table()
al_centro = np.zeros(len(bm0.faces), bool)
visto = np.zeros(len(bm0.faces), bool)
n_islas = 0
n_centro = 0
for f0 in bm0.faces:
    if visto[f0.index]:
        continue
    n_islas += 1
    pila = [f0]
    visto[f0.index] = True
    caras = []
    while pila:
        f = pila.pop()
        caras.append(f.index)
        for e in f.edges:
            for g in e.link_faces:
                if not visto[g.index]:
                    visto[g.index] = True
                    pila.append(g)
    caras = np.array(caras)
    rmin = min(rv[vt.index] for i in caras for vt in bm0.faces[i].verts)
    if rmin < RADIO:
        al_centro[caras] = True
        n_centro += 1
bm0.free()
print("islas %d · al centro %d" % (n_islas, n_centro))


def pieza(nombre, dentro):
    bm = bmesh.new()
    bm.from_mesh(src.data)
    bm.faces.ensure_lookup_table()
    # coordenadas de mundo sobre la propia malla: la pieza sale con transform identidad
    for vt in bm.verts:
        p = m[:3, :3] @ np.array(vt.co[:]) + m[:3, 3]
        vt.co = p.tolist()
    fuera = [f for f in bm.faces if al_centro[f.index] != dentro]
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
