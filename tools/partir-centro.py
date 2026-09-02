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

# islas por conectividad de aristas
bm0 = bmesh.new()
bm0.from_mesh(src.data)
bm0.faces.ensure_lookup_table()
visto = np.zeros(len(bm0.faces), bool)
islas = []
for f0 in bm0.faces:
    if visto[f0.index]:
        continue
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
    vs = np.array(sorted({vt.index for i in caras for vt in bm0.faces[i].verts}))
    z = v[vs, fino] - c[fino]
    islas.append((caras, rv[vs].min(), rv[vs].max(), z.min(), z.max()))
bm0.free()

# a que pieza va cada isla. Tres criterios, medidos en el portal (1-sep-2026):
#  1. entra por debajo de RADIO: es del disco (94 islas)
#  2. LOSA: el disco del vortice es una lamina fina a una altura fija (z +0,00..
#     +0,04 en el portal) y sus islas siguen por debajo del aro hasta r 0,66;
#     las que empiezan entre RADIO y LABIO pero viven ENTERAS en esa losa son
#     disco, no anillo (el anillo baja a z -0,03/-0,09 en esa misma franja).
#     Con solo el criterio 1 asomaban bajo el labio del aro como dientes. La
#     losa se MIDE de las islas del criterio 1 que son casi planas, con un
#     margen de 0,005.
#  3. ASTILLAS: triangulos sueltos (1-3) que cruzan medio radio por la cara
#     superior — basura del remesh que, con el disco escondido, se ve como
#     pinchos hacia el centro. Van con el disco: escondidos en reposo, y
#     abiertos quedan donde siempre estuvieron.
#  4. ISLAS MIXTAS, triangulo a triangulo: la pared interior del aro viene
#     fusionada con trozos del disco (islas de r 0,53-0,70 con z de -0,06 a
#     +0,03), y una isla asi no se puede repartir entera. Dentro de ellas va al
#     centro cada triangulo con la FIRMA del disco: plano (normal por el eje
#     fino), los tres vertices dentro de la losa y que entra por debajo de
#     LABIO. Es la unica parte que corta triangulos, y corta por donde el
#     disco toca la pared —la costura real—, no por un circulo: la pared no
#     es plana y se queda entera.
# La losa se MIDE de los vertices de las islas del criterio 1 que son casi
# planas: percentiles 2-98 mas 0,004. Con min/max una isla que rozaba z -0,008
# bajaba la losa hasta el suelo del anillo (z -0,011..+0,012) y se lo llevaba.
LABIO = float(os.environ.get("LABIO", "0.62"))
LARGO = float(os.environ.get("LARGO", "0.06"))
nrm = np.array([p.normal[:] for p in src.data.polygons])
plano = np.abs(nrm[:, fino]) > 0.7
tri = np.array([p.vertices[:] for p in src.data.polygons])
zv = v[:, fino] - c[fino]
zs = []
for caras, rmin, rmax, zmin, zmax in islas:
    if rmin < RADIO and len(caras) >= 20 and plano[caras].mean() > 0.9:
        zs.append(zv[np.unique(tri[caras])])
if not zs:
    sys.exit("RECHAZAR: ninguna isla plana entra por debajo de r %.2f — no hay disco que partir" % RADIO)
zs = np.concatenate(zs)
losa = (np.percentile(zs, 2) - 0.004, np.percentile(zs, 98) + 0.004)
print("losa del disco: z %+.3f..%+.3f (de %d vertices)" % (losa[0], losa[1], len(zs)))

al_centro = np.zeros(len(src.data.polygons), bool)
cuenta = [0, 0, 0, 0, 0]
for caras, rmin, rmax, zmin, zmax in islas:
    if rmin < RADIO:
        k = 0
    elif rmin < LABIO and zmin >= losa[0] and zmax <= losa[1]:
        k = 1
    elif rmin < LABIO and len(caras) <= 3 and rmax - rmin > 0.15:
        k = 2
    elif rmin < LABIO:
        zt = zv[tri[caras]]
        rt = rv[tri[caras]]
        firma = plano[caras] & (zt.min(1) >= losa[0]) & (zt.max(1) <= losa[1]) & (rt.min(1) < LABIO)
        #  5. LARGO: en el anillo ningun triangulo legitimo cruza mas de ~0,03 de
        #     radio (p95 de la pared interior: 0,02-0,03); uno que cruza 0,06 o
        #     mas por dentro del labio es una astilla del remesh (medidas: 0,07
        #     a 0,39), planas a la altura de la cara superior o inclinadas a la
        #     del disco. Van con el disco, como las astillas de isla entera.
        largo = (rt.max(1) - rt.min(1) > LARGO) & (rt.min(1) < LABIO)
        al_centro[caras[firma | largo]] = True
        cuenta[3] += int(firma.sum())
        cuenta[4] += int((largo & ~firma).sum())
        continue
    else:
        continue
    al_centro[caras] = True
    cuenta[k] += 1
print("islas %d · al centro %d enteras (por radio %d, por losa %d, astillas %d) + %d triangulos de islas mixtas + %d largos"
      % (len(islas), sum(cuenta[:3]), cuenta[0], cuenta[1], cuenta[2], cuenta[3], cuenta[4]))

# INFORME=1: que queda del aro por dentro del labio (lo que asomaria con el
# disco escondido), triangulo a triangulo, para afinar los criterios MIDIENDO
if os.environ.get("INFORME") == "1":
    rt = rv[tri]
    print("--- triangulos del ARO con rmin < %.2f:" % LABIO)
    for caras, rmin, rmax, zmin, zmax in islas:
        q = caras[~al_centro[caras] & (rt[caras].min(1) < LABIO - 0.02)]
        if len(q) == 0:
            continue
        zt = zv[tri[q]]
        print("  isla %5d tris (r %.2f-%.2f) · quedan %3d: plano %3.0f%% · z %+.3f..%+.3f · r %.2f-%.2f · largo p95 %.3f"
              % (len(caras), rmin, rmax, len(q), 100 * plano[q].mean(), zt.min(), zt.max(),
                 rt[q].min(), rt[q].max(), np.percentile(rt[q].max(1) - rt[q].min(1), 95)))


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
