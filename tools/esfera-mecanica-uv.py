"""Prepara la esfera mecanica APROBADA para texturizado PBR: UVs, material IDs, mascara de emision.

Uso:
    blender --background --factory-startup --python tools/esfera-mecanica-uv.py -- \
        source/3d-models/procedural/esfera-mecanica

Lee  esfera-mecanica.blend (geometria aprobada, NO se toca) y escribe la version v2:
    esfera-mecanica-v2-uv.blend / .glb     piezas con UVs y materiales MAT_HULL / MAT_RECESSES / MAT_EMISSION
    uv-layout.png                          islas tintadas por material + aristas
    emission-mask.png                      blanco = emisivo (rasterizado de las caras MAT_EMISSION), sin ruido
    renders/three-quarter-clean.png        render de referencia, clay uniforme, luz blanca suave
    reporte-uv.txt

Lo unico que cambia en la geometria es APLICAR Boolean y Mirror (necesario para que cada
placa tenga su propia isla UV y el desgaste pueda ser asimetrico). Smooth by Angle sigue vivo.

Diales:
"""
import importlib.util
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector

# ----------------------------------------------------------------- diales
TEX_SIZE = 2048
SEAM_ANGLE = 60.0        # aristas con diedro >= 60 grados son costura (base de placas, esquinas, cortes)
                         # los pliegues de 45 grados (tapa->chaflan->muro) NO son costura: se despliegan
PACK_MARGIN = 0.004      # fraccion del UV (~8 px a 2048)
SCALE_BASES = 0.10       # islas enterradas (bases): nunca se ven
SCALE_SPHERE = 0.40      # la esfera solo asoma en las ranuras
WALL_DOT = 0.35          # |n . r| menor => cara de muro (interior de junta)
MASK_DILATE_PX = 4       # sangrado de la mascara para que la costura no muerda negro
RENDER_RES = 2048
RENDER_SAMPLES = 64
# ------------------------------------------------------------------------

MAT_NAMES = ("MAT_HULL", "MAT_RECESSES", "MAT_EMISSION")
MAT_TINT = {"MAT_HULL": (0.72, 0.78, 0.86), "MAT_RECESSES": (0.55, 0.55, 0.55),
            "MAT_EMISSION": (1.0, 0.85, 0.35)}


def load_builder():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("esfera_mecanica", os.path.join(here, "esfera-mecanica.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------- geometria
def apply_geometry_modifiers(ob):
    """Aplica Boolean y Mirror (en orden de pila); deja Smooth by Angle vivo."""
    for m in list(ob.modifiers):
        if m.type in {"BOOLEAN", "MIRROR"}:
            with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
                bpy.ops.object.modifier_apply(modifier=m.name)


def classify_faces(ob, r_sphere):
    """Devuelve lista (por cara) de 'base' | 'wall' | 'top' segun geometria."""
    me = ob.data
    kinds = []
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        if all(v.length < r_sphere - 1e-4 for v in vs):
            kinds.append("base")
            continue
        c = p.center
        radial = c.normalized() if c.length > 1e-9 else Vector((0, 0, 1))
        kinds.append("wall" if abs(p.normal.dot(radial)) < WALL_DOT else "top")
    return kinds


def mark_seams(ob, is_sphere):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = 0
    for e in bm.edges:
        e.seam = False
        if is_sphere:
            a, b = e.verts[0].co, e.verts[1].co
            on_mer = (abs(a.x) < 1e-5 and abs(b.x) < 1e-5) or (abs(a.y) < 1e-5 and abs(b.y) < 1e-5)
            on_eq = abs(a.z) < 1e-5 and abs(b.z) < 1e-5
            e.seam = on_mer or on_eq
        else:
            if len(e.link_faces) == 2 and math.degrees(e.calc_face_angle(0.0)) >= SEAM_ANGLE:
                e.seam = True
            # anillos del nucleo: un corte radial abajo (-Z), fuera de la vista cenital
            a, b = e.verts[0].co, e.verts[1].co
            if ob.name.startswith("Core_") and ob.name != "Core_Lens" and abs(a.x) < 1e-5 and abs(b.x) < 1e-5 and a.z < 0 and b.z < 0:
                e.seam = True
        n += e.seam
    bm.to_mesh(ob.data)
    bm.free()
    return n


def unwrap_all(objs):
    triangulated_master = all(
        len(p.vertices) == 3
        for ob in objs
        for p in ob.data.polygons
    )
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if triangulated_master:
        # Un master triangulado no conserva las caras de control originales. El
        # unwrap por costuras puede plegar triangulos vecinos en bandas curvas;
        # Smart Project crea charts sin pliegues sin tocar la geometria.
        bpy.ops.uv.smart_project(
            angle_limit=math.radians(66.0),
            margin_method="SCALED",
            rotate_method="AXIS_ALIGNED_Y",
            island_margin=0.0,
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=False,
        )
        method = "SMART_PROJECT_TRIANGULATED"
    else:
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
        method = "ANGLE_BASED_SEAMS"
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    return method


def scale_uv_group(ob, face_mask, factor):
    """Escala las UVs de un grupo de caras (islas completas) alrededor de su centro."""
    me = ob.data
    uv = me.uv_layers.active.uv
    loops = [l for p, keep in zip(me.polygons, face_mask) if keep for l in p.loop_indices]
    if not loops:
        return
    pts = np.array([uv[l].vector[:] for l in loops])
    c = pts.mean(axis=0)
    pts = (pts - c) * factor + c
    for l, p in zip(loops, pts):
        uv[l].vector = p


def pack_all(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, rotate_method="ANY", scale=True,
                            merge_overlap=False, margin_method="FRACTION", margin=PACK_MARGIN,
                            pin=False, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


# --------------------------------------------------------- materiales
def make_materials():
    def mat(name, gray, emission=None):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (gray, gray, gray, 1)
        bsdf.inputs["Roughness"].default_value = 0.6
        bsdf.inputs["Metallic"].default_value = 0.0
        if emission is not None:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1)
            bsdf.inputs["Emission Strength"].default_value = 0.0   # apagado hasta la fase de textura
        return m
    return {"MAT_HULL": mat("MAT_HULL", 0.55),
            "MAT_RECESSES": mat("MAT_RECESSES", 0.18),
            "MAT_EMISSION": mat("MAT_EMISSION", 0.85, emission=(1, 1, 1))}


def assign_materials(ob, kinds, mats):
    me = ob.data
    me.materials.clear()
    for n in MAT_NAMES:
        me.materials.append(mats[n])
    idx = {n: i for i, n in enumerate(MAT_NAMES)}
    counts = {n: 0 for n in MAT_NAMES}
    for p, k in zip(me.polygons, kinds):
        if ob.name == "Core_Lens":
            name = "MAT_EMISSION"
        elif ob.name == "Sphere_Core" or k in ("base", "wall"):
            name = "MAT_RECESSES"
        else:
            name = "MAT_HULL"
        p.material_index = idx[name]
        counts[name] += 1
    return counts


# --------------------------------------------------------- raster
def uv_triangles(objs):
    """UVs, material, area, aristas y poligono propietario de cada triangulo."""
    tris, names, areas3d, edges, owners = [], [], [], [], []
    for ob in objs:
        me = ob.data
        me.calc_loop_triangles()
        uv = me.uv_layers.active.uv
        for lt in me.loop_triangles:
            tris.append([uv[l].vector[:] for l in lt.loops])
            names.append(me.materials[me.polygons[lt.polygon_index].material_index].name)
            owners.append((ob, lt.polygon_index))
            v = [me.vertices[i].co for i in lt.vertices]
            areas3d.append((v[1] - v[0]).cross(v[2] - v[0]).length * 0.5)
        for p in me.polygons:
            li = list(p.loop_indices)
            for a, b in zip(li, li[1:] + li[:1]):
                edges.append((uv[a].vector[:], uv[b].vector[:]))
    return np.array(tris), names, np.array(areas3d), edges, owners


def overlapping_triangle_pairs(tris, size):
    """Devuelve pares que comparten al menos un centro de texel, sin contar aristas."""
    owner = np.full((size, size), -1, dtype=np.int32)
    pairs = set()
    for index, tri in enumerate(tris):
        p = tri * size
        x0, y0 = np.floor(p.min(axis=0)).astype(int)
        x1, y1 = np.ceil(p.max(axis=0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        (ax, ay), (bx, by), (cx, cy) = p
        det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(det) < 1e-12:
            continue
        l1 = ((bx - X) * (cy - Y) - (cx - X) * (by - Y)) / det
        l2 = ((cx - X) * (ay - Y) - (ax - X) * (cy - Y)) / det
        l3 = 1.0 - l1 - l2
        inside = (l1 > 1e-7) & (l2 > 1e-7) & (l3 > 1e-7)
        view = owner[y0:y1 + 1, x0:x1 + 1]
        occupied = inside & (view >= 0)
        pairs.update((int(previous), index) for previous in np.unique(view[occupied]))
        view[inside & (view < 0)] = index
    return pairs


def detach_overlapping_polygons(owners, pairs):
    """Separa el UV del segundo poligono de cada par para que el packer lo trate como isla."""
    targets = sorted(
        {owners[second] for _, second in pairs},
        key=lambda item: (item[0].name, item[1]),
    )
    for ordinal, (ob, polygon_index) in enumerate(targets, start=1):
        # Una traslacion subpixel basta para romper la continuidad UV. El pack
        # posterior recoloca y escala la isla; las posiciones 3D no cambian.
        offset = Vector((ordinal * 1.0e-4, ordinal * 1.7e-4))
        uv = ob.data.uv_layers.active.uv
        for loop_index in ob.data.polygons[polygon_index].loop_indices:
            uv[loop_index].vector += offset
    return [f"{ob.name}:{polygon_index}" for ob, polygon_index in targets]


def rasterize(tris, size, select=None, strict=False):
    """Cuenta por pixel cuantos triangulos lo cubren (centro del pixel)."""
    count = np.zeros((size, size), dtype=np.int32)
    eps = 1e-7 if strict else -1e-7
    for i, t in enumerate(tris):
        if select is not None and not select[i]:
            continue
        p = t * size
        x0, y0 = np.floor(p.min(axis=0)).astype(int)
        x1, y1 = np.ceil(p.max(axis=0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        (ax, ay), (bx, by), (cx, cy) = p
        det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(det) < 1e-12:
            continue
        l1 = ((bx - X) * (cy - Y) - (cx - X) * (by - Y)) / det
        l2 = ((cx - X) * (ay - Y) - (ax - X) * (cy - Y)) / det
        l3 = 1.0 - l1 - l2
        inside = (l1 > eps) & (l2 > eps) & (l3 > eps)
        count[y0:y1 + 1, x0:x1 + 1] += inside
    return count


def dilate(mask, px):
    m = mask.copy()
    for _ in range(px):
        n = m.copy()
        n[1:, :] |= m[:-1, :]
        n[:-1, :] |= m[1:, :]
        n[:, 1:] |= m[:, :-1]
        n[:, :-1] |= m[:, 1:]
        m = n
    return m


def label_components(mask):
    """Lista (px, centro u, centro v) de cada mancha blanca de la mascara."""
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        if seen[y, x]:
            continue
        stack, px, sy, sx = [(y, x)], 0, 0, 0
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            px += 1; sy += cy; sx += cx
            for ny, nx in ((cy+1, cx), (cy-1, cx), (cy, cx+1), (cy, cx-1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        out.append((px, round(sx / px / mask.shape[1], 3), round(sy / px / mask.shape[0], 3)))
    return out


def save_png(path, rgb):
    """rgb: HxWx3 float 0..1, fila 0 = abajo (convencion de Blender)."""
    h, w, _ = rgb.shape
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    px = np.concatenate([rgb, np.ones((h, w, 1), dtype=np.float32)], axis=2).astype(np.float32)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def draw_layout(tris, names, edges, size, path):
    rgb = np.ones((size, size, 3), dtype=np.float32)
    for n in MAT_NAMES:
        sel = [nm == n for nm in names]
        cov = rasterize(tris, size, select=sel) > 0
        rgb[cov] = MAT_TINT[n]
    for (a, b) in edges:
        a = np.array(a) * size
        b = np.array(b) * size
        steps = int(max(abs(b - a).max(), 1)) * 2 + 1
        t = np.linspace(0, 1, steps)
        xs = np.clip((a[0] + (b[0] - a[0]) * t).astype(int), 0, size - 1)
        ys = np.clip((a[1] + (b[1] - a[1]) * t).astype(int), 0, size - 1)
        rgb[ys, xs] = (0.1, 0.1, 0.1)
    save_png(path, rgb)


# --------------------------------------------------------- render de referencia
def clean_render(scene, objs, out_path):
    clay = bpy.data.materials.new("Clay_Reference")
    clay.use_nodes = True
    bsdf = clay.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    saved = {}
    for ob in objs:
        saved[ob.name] = [s.material for s in ob.material_slots]
        for s in ob.material_slots:
            s.material = clay

    for ob in list(scene.collection.all_objects):
        if ob.type == "LIGHT":
            ob.hide_render = True
    world = bpy.data.worlds.new("Reference_World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.40, 0.40, 0.40, 1)
    bg.inputs[1].default_value = 1.0
    old_world = scene.world
    scene.world = world

    def area(name, loc, energy, size):
        li = bpy.data.lights.new(name, "AREA")
        li.energy = energy
        li.size = size
        li.color = (1, 1, 1)
        ob = bpy.data.objects.new(name, li)
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)
        return ob

    lights = [area("Ref_Key", (-3, -5, 6), 320, 8.0),
              area("Ref_Fill", (6, -3, 2), 110, 8.0),
              area("Ref_Back", (2, 6, 3), 70, 8.0)]

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = RENDER_RES
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = RENDER_SAMPLES
        for attr in ("use_gtao", "use_bloom", "use_raytracing"):
            if hasattr(eevee, attr):
                setattr(eevee, attr, False)
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "None"
    except TypeError:
        pass
    scene.camera = bpy.data.objects["Cam_ThreeQuarter"]
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)

    # restaurar (no se guarda nada de esto en el .blend v2)
    for ob in objs:
        for s, m in zip(ob.material_slots, saved[ob.name]):
            s.material = m
    for l in lights:
        bpy.data.objects.remove(l)
    scene.world = old_world
    for ob in list(scene.collection.all_objects):
        if ob.type == "LIGHT":
            ob.hide_render = False


# --------------------------------------------------------- main
def main():
    builder = load_builder()
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = os.path.abspath(argv[0])
    src = os.path.join(out_dir, "esfera-mecanica.blend")
    bpy.ops.wm.open_mainfile(filepath=src)
    scene = bpy.context.scene
    R = builder.R_SPHERE

    parts = [o for o in bpy.data.collections["MechSphere"].objects if o.type == "MESH"]
    parts.sort(key=lambda o: o.name)
    sphere = bpy.data.objects["Sphere_Core"]
    lines = []

    tris_before = 0
    for o in parts:
        bm = builder.evaluated_bmesh(o)
        tris_before += sum(len(f.verts) - 2 for f in bm.faces)
        bm.free()

    # 1) geometria real (Boolean + Mirror aplicados), costuras y despliegue
    for ob in parts:
        apply_geometry_modifiers(ob)
        if not ob.data.uv_layers:
            ob.data.uv_layers.new(name="UVMap")
        n = mark_seams(ob, ob is sphere)
        lines.append(f"  costuras {ob.name:22s} {n:4d}")
    uv_method = unwrap_all(parts)
    lines.append(f"metodo UV: {uv_method}")

    # 2) material IDs por geometria
    mats = make_materials()
    kinds = {ob.name: classify_faces(ob, R) for ob in parts}
    lines.append("materiales por pieza (caras):")
    totals = {n: 0 for n in MAT_NAMES}
    for ob in parts:
        c = assign_materials(ob, kinds[ob.name], mats)
        for n in MAT_NAMES:
            totals[n] += c[n]
        lines.append(f"  {ob.name:22s} " + "  ".join(f"{n}={c[n]}" for n in MAT_NAMES))
    lines.append("  TOTAL                  " + "  ".join(f"{n}={totals[n]}" for n in MAT_NAMES))

    # 3) densidad: bajar lo que no se ve, empaquetar todo en un solo 0..1
    for ob in parts:
        if ob is sphere:
            scale_uv_group(ob, [True] * len(ob.data.polygons), SCALE_SPHERE)
        elif uv_method != "SMART_PROJECT_TRIANGULATED":
            # En el master de control las bases son islas completas. En un
            # master triangulado la seleccion puede cortar un chart y volver a
            # introducir pliegues, asi que conserva densidad uniforme.
            scale_uv_group(ob, [k == "base" for k in kinds[ob.name]], SCALE_BASES)
    pack_all(parts)

    # Smart Project evita la gran mayoria de pliegues, pero una chart muy
    # concava puede conservar cruces internos. Aisla solo los poligonos
    # implicados y vuelve a empacar; es una operacion exclusivamente UV.
    detached = []
    if uv_method == "SMART_PROJECT_TRIANGULATED":
        for _ in range(4):
            trial_tris, _, _, _, trial_owners = uv_triangles(parts)
            pairs = overlapping_triangle_pairs(trial_tris, TEX_SIZE)
            if not pairs:
                break
            repaired = detach_overlapping_polygons(trial_owners, pairs)
            detached.extend(item for item in repaired if item not in detached)
            pack_all(parts)
    lines.append(f"reparacion UV de pliegues: poligonos aislados={detached}")

    # 4) validacion UV
    tris, names, areas3d, edges, _ = uv_triangles(parts)
    in_range = bool((tris >= -1e-6).all() and (tris <= 1 + 1e-6).all())
    cover = rasterize(tris, TEX_SIZE, strict=True)
    overlap_px = int((cover > 1).sum())
    used = float((cover > 0).mean())
    uv_area = np.abs((tris[:, 1, 0] - tris[:, 0, 0]) * (tris[:, 2, 1] - tris[:, 0, 1])
                     - (tris[:, 2, 0] - tris[:, 0, 0]) * (tris[:, 1, 1] - tris[:, 0, 1])) * 0.5
    vis = np.array([n != "MAT_RECESSES" for n in names])   # tapas, chaflanes y lente
    dens = np.sqrt(uv_area[vis] / np.maximum(areas3d[vis], 1e-12)) * TEX_SIZE
    w = areas3d[vis]
    d_mean = float((dens * w).sum() / w.sum())
    d_lo, d_hi = float(np.percentile(dens, 5)), float(np.percentile(dens, 95))
    lines.append(f"UV: en rango 0..1={in_range}  pixeles con solape={overlap_px}  "
                 f"ocupacion={used*100:.1f}%  texeles/unidad (visibles): media={d_mean:.0f} "
                 f"p5={d_lo:.0f} p95={d_hi:.0f}")

    # 5) mascara de emision y layout
    emis = [n == "MAT_EMISSION" for n in names]
    mask = dilate(rasterize(tris, TEX_SIZE, select=emis) > 0, MASK_DILATE_PX)
    save_png(os.path.join(out_dir, "emission-mask.png"), np.repeat(mask[:, :, None], 3, axis=2).astype(np.float32))
    draw_layout(tris, names, edges, TEX_SIZE, os.path.join(out_dir, "uv-layout.png"))
    lab = label_components(mask)
    lines.append(f"mascara: componentes blancos={lab}")
    lines.append(f"mascara: {int(mask.sum())} px blancos de {TEX_SIZE*TEX_SIZE} ({mask.mean()*100:.2f}%), "
                 f"sangrado {MASK_DILATE_PX} px, valores solo 0/1")

    # 6) geometria sigue sana
    vlines, ok, tv, tt = builder.verify(parts, sphere)
    lines += vlines
    lines.append(f"triangulos evaluados antes={tris_before} despues={tt}")

    # 7) guardar v2, exportar, render de referencia
    blend = os.path.join(out_dir, "esfera-mecanica-v2-uv.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    glb = os.path.join(out_dir, "esfera-mecanica-v2-uv.glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(o in parts)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_texcoords=True,
                              export_normals=True, export_animations=False, export_skins=False)
    nmesh, gv, gt, size = builder.glb_counts(glb)
    lines.append(f"GLB v2: mallas={nmesh} vertices={gv} triangulos={gt} bytes={size}")

    clean_render(scene, parts, os.path.join(out_dir, "renders", "three-quarter-clean.png"))

    with open(os.path.join(out_dir, "reporte-uv.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
