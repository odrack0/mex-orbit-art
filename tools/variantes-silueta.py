# Saca VARIANTES game-ready de una nave hard-surface de Meshy (alto, 1,5-3 M tris)
# para ELEGIR que presupuesto conserva mejor la silueta y los cambios de plano.
# No es una reduccion directa de millones a 5 k: primero se repara la malla, luego
# se quita la triangulacion inutil de las superficies planas (Decimate PLANAR) y
# solo despues se colapsa cada presupuesto POR SEPARADO desde la misma fuente.
#
#   blender --background --factory-startup --python tools/variantes-silueta.py -- \
#       <alto.glb> <carpeta_salida> [planar=1] [tris=30000,20000,15000,10000,8000,5000]
#
# Objetos que quedan en la escena (y en el .blend que se guarda en la salida):
#   MASTER_ORIGINAL   el GLB tal cual (solo unido en un objeto y con transform aplicada)
#   MASTER_REPAIRED   validado, sin degenerados, merge conservador, sin sueltos,
#                     normales recalculadas, agujeros PEQUENIOS cerrados
#   CLEAN_SOURCE      MASTER_REPAIRED + Decimate PLANAR a `planar` grados
#   <nombre>_<N>k_A   Collapse desde CLEAN_SOURCE, sin shrinkwrap
#   <nombre>_<N>k_B   igual + Shrinkwrap a MASTER_REPAIRED (nearest surface, offset 0)
#
# Diales (relativos a la diagonal de la caja del modelo, para no depender de la
# escala con que exporte Meshy):
#   MERGE_REL     1e-5 · diag   merge by distance: solo vertices exactamente duplicados
#   ISLA_MIN      100 caras     islas con menos caras se consideran basura (cubo de Meshy)
#   AGUJERO_*     16 lados y 2 % · diag de perimetro: agujeros mas grandes NO se tocan,
#                 solo se reportan (pueden ser cavidades reales del disenio)
#   SIMETRIA_REL  mediana de distancia espejo < 0,3 % · diag para activar la simetria
#                 del Collapse en ese eje
#   SUAVE_GRADOS  30°: caras suaves y arista dura donde dos caras se doblan mas que eso.
#                 Sin esto el GLB lleva 3 vertices por triangulo (caras planas partidas)
# La metrica de silueta de cada variante es la distancia de una muestra de vertices
# de MASTER_REPAIRED a la superficie de la variante (lo que la variante PIERDE) y de
# los vertices de la variante a MASTER_REPAIRED (lo que INVENTA), en % de la diagonal.
import bpy, bmesh, os, sys, math, time, random
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree


args = sys.argv[sys.argv.index("--") + 1:]
if len(args) < 2:
    sys.exit("uso: variantes-silueta.py <alto.glb> <carpeta_salida> [planar_grados] [tris,tris,...]")
alto_p, salida_dir = os.path.abspath(args[0]), os.path.abspath(args[1])
PLANAR_GRADOS = float(args[2]) if len(args) > 2 else 1.0
PRESUPUESTOS = [int(x) for x in args[3].split(",")] if len(args) > 3 else [30000, 20000, 15000, 10000, 8000, 5000]
NOMBRE = os.path.splitext(os.path.basename(alto_p))[0]
MERGE_REL, ISLA_MIN, AGUJERO_LADOS, AGUJERO_REL, SIMETRIA_REL = 1e-5, 100, 16, 0.02, 0.003
SUAVE_GRADOS, MUESTRA = 30.0, 100000
os.makedirs(salida_dir, exist_ok=True)
t0 = time.time()
informe = []


def log(msg):
    print("[%5.0f s] %s" % (time.time() - t0, msg), flush=True)
    informe.append(msg)


bpy.ops.wm.read_factory_settings(use_empty=True)
esc = bpy.context.scene
col = esc.collection


def tris(obj):
    m = obj.data
    if not len(m.polygons):
        return 0
    lt = np.empty(len(m.polygons), dtype=np.int32)
    m.polygons.foreach_get("loop_total", lt)
    return int((lt - 2).sum())


def duplicar(obj, nombre):
    n = obj.copy()
    n.data = obj.data.copy()
    n.name, n.data.name = nombre, nombre
    col.objects.link(n)
    return n


def aplicar(obj, mod):
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                   selected_editable_objects=[obj]):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def coords(obj):
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


# ---------------------------------------------------------------- 1. MASTER_ORIGINAL
antes = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=alto_p)
nuevos = [o for o in bpy.data.objects if o not in antes and o.type == "MESH"]
if not nuevos:
    sys.exit("RECHAZAR: %s no trae mallas" % alto_p)
for o in nuevos:
    o.data.transform(o.matrix_world)   # headless no evalua el depsgraph: a la malla
    o.matrix_world.identity()
    o.select_set(True)
bpy.context.view_layer.objects.active = nuevos[0]
if len(nuevos) > 1:
    with bpy.context.temp_override(active_object=nuevos[0], selected_editable_objects=nuevos):
        bpy.ops.object.join()
original = bpy.context.view_layer.objects.active
original.name = original.data.name = "MASTER_ORIGINAL"
for o in [o for o in bpy.data.objects if o not in antes and o.type != "MESH"]:
    bpy.data.objects.remove(o, do_unlink=True)
original.select_set(False)
co = coords(original)
bmin, bmax = co.min(axis=0), co.max(axis=0)
DIAG = float(np.linalg.norm(bmax - bmin))
log("MASTER_ORIGINAL: %d objetos unidos · %d verts · %d tris · caja %.3f x %.3f x %.3f · diag %.3f" % (
    len(nuevos), len(original.data.vertices), tris(original), *(bmax - bmin), DIAG))

# ---------------------------------------------------------------- 2-3. MASTER_REPAIRED
rep = duplicar(original, "MASTER_REPAIRED")
m = rep.data
if m.validate(verbose=False, clean_customdata=True):
    log("validate: la malla traia datos invalidos y Blender los corrigio")
else:
    log("validate: malla valida")
bm = bmesh.new()
bm.from_mesh(m)
nv, ne, nf = len(bm.verts), len(bm.edges), len(bm.faces)
bmesh.ops.dissolve_degenerate(bm, dist=DIAG * 1e-7, edges=bm.edges[:])
log("degenerados: -%d verts, -%d aristas, -%d caras" % (nv - len(bm.verts), ne - len(bm.edges), nf - len(bm.faces)))
nv = len(bm.verts)
# remove_doubles tarda 20 min en 1 M de verts aunque no fusione nada (medido, Blender 5.2):
# antes se mira con una rejilla numpy si hay candidatos a la distancia del merge
co_bm = np.array([v.co[:] for v in bm.verts])
celdas = np.unique(np.round(co_bm / (DIAG * MERGE_REL)).astype(np.int64), axis=0)
if len(celdas) < nv:
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=DIAG * MERGE_REL)
    log("merge by distance (%.2e = %.0e·diag): -%d verts" % (DIAG * MERGE_REL, MERGE_REL, nv - len(bm.verts)))
else:
    log("merge by distance (%.2e = %.0e·diag): sin candidatos en la rejilla, se salta" % (DIAG * MERGE_REL, MERGE_REL))
sueltos_v = [v for v in bm.verts if not v.link_edges]
sueltos_e = [e for e in bm.edges if not e.link_faces]
bmesh.ops.delete(bm, geom=sueltos_e, context="EDGES")
bmesh.ops.delete(bm, geom=[v for v in sueltos_v if v.is_valid], context="VERTS")
log("sueltos: -%d verts sin arista, -%d aristas sin cara" % (len(sueltos_v), len(sueltos_e)))
bm.to_mesh(m)
bm.free()

# islas (componentes conexas) con numpy + union-find: la basura de Meshy es un cubo de 12 tris
ev = np.empty(len(m.edges) * 2, dtype=np.int64)
m.edges.foreach_get("vertices", ev)
ev = ev.reshape(-1, 2)
padre = np.arange(len(m.vertices))


def raiz(i):
    while padre[i] != i:
        padre[i] = padre[padre[i]]
        i = padre[i]
    return i


for a, b in ev.tolist():
    ra, rb = raiz(a), raiz(b)
    if ra != rb:
        padre[ra] = rb
comp = np.array([raiz(i) for i in range(len(padre))])
loop_start = np.empty(len(m.polygons), dtype=np.int64)
m.polygons.foreach_get("loop_start", loop_start)
loop_v = np.empty(len(m.loops), dtype=np.int64)
m.loops.foreach_get("vertex_index", loop_v)
comp_cara = comp[loop_v[loop_start]]
ids, cuentas = np.unique(comp_cara, return_counts=True)
orden = np.argsort(-cuentas)
log("islas: %d · mayores: %s" % (len(ids), ", ".join("%d caras" % cuentas[i] for i in orden[:8])))
basura = ids[cuentas < ISLA_MIN]
if len(basura):
    co = coords(rep)
    for cid in basura[:20]:
        vs = co[comp == cid]
        log("  isla basura: %d caras · caja %.4f x %.4f x %.4f · centro (%.3f, %.3f, %.3f)" % (
            cuentas[ids == cid][0], *(vs.max(axis=0) - vs.min(axis=0)), *vs.mean(axis=0)))
    quitar = np.isin(comp, basura)
    bm = bmesh.new()
    bm.from_mesh(m)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(quitar)[0].tolist()], context="VERTS")
    bm.to_mesh(m)
    bm.free()
    log("islas basura eliminadas: %d (%d caras en total, umbral < %d caras)" % (
        len(basura), int(cuentas[cuentas < ISLA_MIN].sum()), ISLA_MIN))
else:
    log("islas basura: ninguna (umbral < %d caras)" % ISLA_MIN)

bm = bmesh.new()
bm.from_mesh(m)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
nm_e = [e for e in bm.edges if not e.is_manifold]
borde = [e for e in nm_e if e.is_boundary]
nm_v = sum(1 for v in bm.verts if not v.is_manifold)
log("non-manifold: %d aristas (%d de borde, %d con >2 caras) · %d vertices" % (
    len(nm_e), len(borde), len(nm_e) - len(borde), nm_v))

# agujeros = componentes conexas de aristas de borde
adj = {}
for e in borde:
    for v in e.verts:
        adj.setdefault(v.index, []).append(e)
visto, agujeros = set(), []
for e in borde:
    if e.index in visto:
        continue
    cola, grupo = [e], []
    visto.add(e.index)
    while cola:
        x = cola.pop()
        grupo.append(x)
        for v in x.verts:
            for y in adj[v.index]:
                if y.index not in visto:
                    visto.add(y.index)
                    cola.append(y)
    agujeros.append(grupo)
pequenios, grandes = [], []
for g in agujeros:
    per = sum(e.calc_length() for e in g)
    (pequenios if len(g) <= AGUJERO_LADOS and per <= DIAG * AGUJERO_REL else grandes).append((g, per))
log("agujeros: %d en total · %d pequenios (<= %d lados y <= %.0f %% diag) · %d GRANDES" % (
    len(agujeros), len(pequenios), AGUJERO_LADOS, AGUJERO_REL * 100, len(grandes)))
grandes.sort(key=lambda gp: -gp[1])
for g, per in grandes[:40]:
    vs = np.array([v.co[:] for e in g for v in e.verts])
    log("  agujero GRANDE no tocado: %d aristas · perimetro %.1f %% diag · caja %.3f x %.3f x %.3f · centro (%.3f, %.3f, %.3f)" % (
        len(g), per / DIAG * 100, *(vs.max(axis=0) - vs.min(axis=0)), *vs.mean(axis=0)))
if len(grandes) > 40:
    log("  ... y %d agujeros grandes mas" % (len(grandes) - 40))
if pequenios:
    aristas = [e for g, _ in pequenios for e in g]
    r = bmesh.ops.holes_fill(bm, edges=aristas, sides=AGUJERO_LADOS)
    nuevas = r["faces"]
    if nuevas:
        bmesh.ops.triangulate(bm, faces=nuevas, quad_method="BEAUTY", ngon_method="BEAUTY")
    log("agujeros pequenios cerrados: %d caras nuevas para %d agujeros" % (len(nuevas), len(pequenios)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(m)
bm.free()
m.update()
log("MASTER_REPAIRED: %d verts · %d tris" % (len(m.vertices), tris(rep)))

# ---------------------------------------------------------------- 4-5. CLEAN_SOURCE (planar)
clean = duplicar(rep, "CLEAN_SOURCE")
antes_t = tris(clean)
mod = clean.modifiers.new("planar", "DECIMATE")
mod.decimate_type = "DISSOLVE"
mod.angle_limit = math.radians(PLANAR_GRADOS)
mod.use_dissolve_boundaries = False
mod.delimit = {"NORMAL"}
aplicar(clean, mod)
# el planar deja ngonos: se triangulan ya, para que el Collapse arranque de triangulos limpios
mod = clean.modifiers.new("tri", "TRIANGULATE")
mod.quad_method, mod.ngon_method = "BEAUTY", "BEAUTY"
aplicar(clean, mod)
clean_t = tris(clean)
log("CLEAN_SOURCE: Decimate PLANAR %.1f° -> %d tris (%.1f %% del reparado), %d verts" % (
    PLANAR_GRADOS, clean_t, clean_t / antes_t * 100, len(clean.data.vertices)))

# ---------------------------------------------------------------- simetria
co = coords(clean)
centro = (co.min(axis=0) + co.max(axis=0)) / 2
# distancia del espejo de cada vertice a la SUPERFICIE (BVH nativo; un KDTree llenado
# desde Python tardaba 12 min con 700 k verts)
bvh_clean = BVHTree.FromObject(clean, bpy.context.evaluated_depsgraph_get())
rng = random.Random(7)
idx = rng.sample(range(len(co)), min(5000, len(co)))
puntajes = []
for eje in range(3):
    ds = []
    for i in idx:
        p = co[i].copy()
        p[eje] = 2 * centro[eje] - p[eje]
        ds.append(bvh_clean.find_nearest(Vector(p))[3])
    puntajes.append(float(np.median(ds)) / DIAG)
log("simetria (mediana espejo / diag): X %.4f · Y %.4f · Z %.4f" % tuple(puntajes))
eje_sim = int(np.argmin(puntajes))
usar_sim = puntajes[eje_sim] < SIMETRIA_REL
desplaza = Vector((0, 0, 0))
if usar_sim:
    desplaza[eje_sim] = -centro[eje_sim]
    log("simetria: SI, eje %s (plano en %s = %.4f)" % ("XYZ"[eje_sim], "xyz"[eje_sim], centro[eje_sim]))
else:
    log("simetria: NO (ningun eje baja de %.3f)" % SIMETRIA_REL)

# ---------------------------------------------------------------- metrica de silueta
bvh_rep = BVHTree.FromObject(rep, bpy.context.evaluated_depsgraph_get())
co_rep = coords(rep)
muestra_rep = [Vector(p) for p in co_rep[rng.sample(range(len(co_rep)), min(MUESTRA, len(co_rep)))].tolist()]


def desviacion(obj):
    """((pierde mean, p99), (inventa mean, p99)) en % de la diagonal."""
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    d1 = np.array([bvh.find_nearest(p)[3] for p in muestra_rep]) / DIAG * 100
    d2 = np.array([bvh_rep.find_nearest(Vector(p))[3] for p in coords(obj).tolist()]) / DIAG * 100
    return (d1.mean(), np.percentile(d1, 99)), (d2.mean(), np.percentile(d2, 99))


# ---------------------------------------------------------------- 6-9. variantes
filas = []


def exportar(obj, ruta):
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=ruta, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True)
    obj.select_set(False)
    return os.path.getsize(ruta) / 1048576.0


def colapsar(obj, objetivo):
    """Collapse hasta `objetivo` tris; reintenta si el conteo se desvia mas de 3 %."""
    respaldo = obj.data.copy()
    ratio = objetivo / clean_t
    for intento in range(3):
        obj.data.transform(Matrix.Translation(desplaza))
        mod = obj.modifiers.new("collapse", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        mod.use_symmetry = usar_sim
        mod.symmetry_axis = "XYZ"[eje_sim]
        aplicar(obj, mod)
        obj.data.transform(Matrix.Translation(-desplaza))
        n = tris(obj)
        if abs(n - objetivo) / objetivo <= 0.03 or intento == 2:
            break
        log("  %d tris con ratio %.5f, se reintenta" % (n, ratio))
        ratio *= objetivo / n
        viejo = obj.data
        obj.data = respaldo.copy()
        bpy.data.meshes.remove(viejo)
    bpy.data.meshes.remove(respaldo)
    return n


def triangular(obj):
    """Triangula y deja el sombreado game-ready: caras suaves con aristas duras por angulo.
    Sin esto todas las caras salen planas y el exportador parte 3 vertices por triangulo."""
    mod = obj.modifiers.new("tri", "TRIANGULATE")
    mod.quad_method, mod.ngon_method = "BEAUTY", "BEAUTY"
    aplicar(obj, mod)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    umbral = math.radians(SUAVE_GRADOS)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > umbral)
    bm.to_mesh(obj.data)
    bm.free()


for objetivo in PRESUPUESTOS:
    etiqueta = "%s_%dk" % (NOMBRE, objetivo // 1000)
    a = duplicar(clean, etiqueta + "_A")
    colapsar(a, objetivo)
    triangular(a)
    b = duplicar(a, etiqueta + "_B")
    mod = b.modifiers.new("shrinkwrap", "SHRINKWRAP")
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    mod.target = rep
    mod.offset = 0.0
    aplicar(b, mod)
    triangular(b)
    for obj, sufijo in ((a, "A-sin-shrinkwrap"), (b, "B-shrinkwrap")):
        ruta = os.path.join(salida_dir, "%s_%s.glb" % (etiqueta, sufijo))
        mb = exportar(obj, ruta)
        (p1, p2), (i1, i2) = desviacion(obj)
        filas.append((os.path.basename(ruta), tris(obj), len(obj.data.vertices), mb, p1, p2, i1, i2))
        log("%s: %d tris · %d verts · %.2f MB · pierde mean %.3f %% p99 %.3f %% · inventa mean %.3f %% p99 %.3f %%" % (
            os.path.basename(ruta), tris(obj), len(obj.data.vertices), mb, p1, p2, i1, i2))

# ---------------------------------------------------------------- informe y .blend
tabla = ["", "| archivo | tris | verts | MB | pierde mean % | pierde p99 % | inventa mean % | inventa p99 % |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
for f in filas:
    tabla.append("| %s | %d | %d | %.2f | %.3f | %.3f | %.3f | %.3f |" % f)
tabla += ["", "«pierde» = distancia de una muestra de %d vertices de MASTER_REPAIRED a la superficie de la variante"
          " (detalle/silueta que la variante ya no cubre). «inventa» = distancia de los vertices de la variante a"
          " MASTER_REPAIRED (cuanto se separa de la superficie real; en las B es ~0 por construccion)."
          " Todo en %% de la diagonal de la caja (%.3f)." % (len(muestra_rep), DIAG)]
with open(os.path.join(salida_dir, "informe.md"), "w", encoding="utf-8") as f:
    f.write("# Variantes de silueta de %s\n\n" % NOMBRE)
    f.write("Generado por tools/variantes-silueta.py · Blender %s · planar %.1f°\n\n" % (bpy.app.version_string, PLANAR_GRADOS))
    f.write("```\n" + "\n".join(informe) + "\n```\n")
    f.write("\n".join(tabla) + "\n")
for o in bpy.data.objects:
    o.hide_set(o.name != "MASTER_REPAIRED")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(salida_dir, NOMBRE + "_variantes.blend"), compress=True)
log("listo: %d GLB + informe.md + %s_variantes.blend en %s" % (len(filas), NOMBRE, salida_dir))
