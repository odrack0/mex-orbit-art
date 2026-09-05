"""Esfera mecanica procedural (asset top-down) construida con bmesh + modificadores.

Uso:
    blender --background --factory-startup --python tools/esfera-mecanica.py -- <carpeta_salida>

Produce en <carpeta_salida>:
    esfera-mecanica.blend     escena con las piezas y modificadores sin aplicar
    esfera-mecanica.glb       exportacion con modificadores aplicados (solo las piezas)
    renders/*.png             front, back, left, right, top, three-quarter + contact-sheet.png
    reporte.txt               verificacion de geometria y conteo final

Diseno (interpretacion industrial del concepto):
    - Sphere_Core:      esfera UV perfecta de radio 1, cerrada. NUNCA se toca.
    - Placas:           parches de esfera (grilla lon/lat) con chaflan, muros radiales y base
                        hundida 0.02 dentro de la esfera (cada placa es un solido cerrado).
                        Costuras de latitud +-20 / +-52 / +-80 grados; las bandas van a
                        tresbolillo (0/60 arriba, 30/90 en el ecuador, 45/135 en el casquete).
    - Hub_Pole:         disco en cada polo (10 grados de radio angular).
    - Nucleo frontal:   eje -Y. Bisel exterior (anillo), aro interior (anillo) y lente (disco).
                        El corte circular alrededor del nucleo lo hace un Boolean con un cono
                        (Cutter_CoreCone) cuyo vertice esta en el origen.
    - Las lineas cyan NO se modelan: seran textura/emission.

Diales (grados salvo que se indique lo contrario):
"""
import bpy
import bmesh
import json
import math
import os
import struct
import sys
from math import asin, cos, radians, sin
from mathutils import Vector

# ----------------------------------------------------------------- diales
R_SPHERE = 1.0          # radio de la esfera principal
SPHERE_SEGMENTS = 32    # esfera UV: segmentos (lon)
SPHERE_RINGS = 16       # esfera UV: anillos (lat)

GROOVE_HALF = 1.5       # medio ancho de la ranura entre placas (angular)
PLATE_HEIGHT = 0.05     # cuanto sobresale una placa sobre la esfera
PLATE_CHAMFER = 0.012   # chaflan de 45 grados en el borde superior
BASE_SINK = 0.02        # cuanto se hunde la base de cada pieza bajo la superficie (evita z-fighting)

LAT_SEAMS = (20.0, 52.0, 80.0)          # costuras de latitud (simetricas en Z)
BAND_EQ_SEAMS = (30, 90, 150, 210, 270, 330)   # frente (330..30) reservado al nucleo
BAND_UP_SEAMS = (0, 60, 120, 180, 240, 300)
CAP_SEAMS = (45, 135, 225, 315)
PLATE_NLON = 4          # subdivisiones a lo largo de una placa
PLATE_NLAT = {"eq": 3, "up": 2, "cap": 2}

HUB_RHO = 10.0          # radio angular del disco polar (medido a la costura)
HUB_HEIGHT = 0.05

CORE_CONE_HALF = 36.0   # semiangulo del cono que recorta las placas alrededor del nucleo
CORE_BEZEL = (21.0, 30.0, 0.08)     # anillo exterior: rho_in, rho_out, altura
CORE_RIM = (14.5, 19.0, 0.05)       # aro interior
CORE_LENS = (13.0, 0.035)           # lente central: rho_out, altura (sera el cyan emisivo)
CORE_SEGMENTS = 24      # segmentos angulares de anillos y lente

SMOOTH_ANGLE = 30.0     # Smooth by Angle: aristas mas abiertas quedan duras

RENDER_RES = 1024
RENDER_SAMPLES = 32
# ------------------------------------------------------------------------


def rad(d):
    return radians(d)


def dir_lonlat(lon, lat):
    """lon 0 = frente (-Y), crece hacia +X; lat 0 = ecuador, +90 = polo +Z."""
    cl = cos(rad(lat))
    return Vector((sin(rad(lon)) * cl, -cos(rad(lon)) * cl, sin(rad(lat))))


AXIS_FRONT = (Vector((0, -1, 0)), Vector((1, 0, 0)), Vector((0, 0, 1)))
AXIS_POLE = (Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 1, 0)))


def dir_polar(frame, phi, rho):
    """Punto a distancia angular rho del eje del frame, azimut phi."""
    a, u, v = frame
    return a * cos(rad(rho)) + (u * cos(rad(phi)) + v * sin(rad(phi))) * sin(rad(rho))


def lon_inset(lat, ang):
    """Desplazamiento en longitud para alejarse 'ang' (angular real) de un meridiano."""
    s = sin(rad(ang)) / max(cos(rad(lat)), 1e-6)
    return math.degrees(asin(min(s, 1.0)))


def linspace(a, b, n):
    return [a + (b - a) * i / n for i in range(n + 1)]


# --------------------------------------------------------- generadores
def add_plate_rect(bm, lon0, lon1, lat0, lat1, nlon, nlat, height, r_base=None):
    """Placa entre costuras (lon0..lon1, lat0..lat1). Solido cerrado apoyado en la esfera."""
    r_top = R_SPHERE + height
    r_base = R_SPHERE - BASE_SINK if r_base is None else r_base
    c = PLATE_CHAMFER
    c_ang = math.degrees(c / r_top)
    g = GROOVE_HALF

    lats = linspace(lat0 + g, lat1 - g, nlat)
    grid = []
    params = []
    for lat in lats:
        dl = lon_inset(lat, g)
        lons = linspace(lon0 + dl, lon1 - dl, nlon)
        grid.append([bm.verts.new(dir_lonlat(lo, lat) * r_top) for lo in lons])
        params.append([(lo, lat) for lo in lons])

    for i in range(nlat):
        for j in range(nlon):
            bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))

    boundary = [(0, j) for j in range(nlon)]
    boundary += [(i, nlon) for i in range(nlat)]
    boundary += [(nlat, j) for j in range(nlon, 0, -1)]
    boundary += [(i, 0) for i in range(nlat, 0, -1)]

    top_loop, cham_loop, base_loop = [], [], []
    for (i, j) in boundary:
        lo, la = params[i][j]
        la2 = la - c_ang if i == 0 else (la + c_ang if i == nlat else la)
        dl = lon_inset(la, c_ang)
        lo2 = lo - dl if j == 0 else (lo + dl if j == nlon else lo)
        d = dir_lonlat(lo2, la2)
        top_loop.append(grid[i][j])
        cham_loop.append(bm.verts.new(d * (r_top - c)))
        base_loop.append(bm.verts.new(d * r_base))
    _close_skirt(bm, top_loop, cham_loop, base_loop)


def _close_skirt(bm, top_loop, cham_loop, base_loop):
    n = len(top_loop)
    for k in range(n):
        k2 = (k + 1) % n
        bm.faces.new((top_loop[k], cham_loop[k], cham_loop[k2], top_loop[k2]))
        bm.faces.new((cham_loop[k], base_loop[k], base_loop[k2], cham_loop[k2]))
    bm.faces.new(tuple(reversed(base_loop)))


def add_disc(bm, frame, rho_out, nphi, height, mid_ring=True):
    """Disco de radio angular rho_out alrededor del eje del frame."""
    r_top = R_SPHERE + height
    r_base = R_SPHERE - BASE_SINK
    c = PLATE_CHAMFER
    c_ang = math.degrees(c / r_top)
    phis = [360.0 * k / nphi for k in range(nphi)]

    center = bm.verts.new(frame[0] * r_top)
    top = [bm.verts.new(dir_polar(frame, p, rho_out) * r_top) for p in phis]
    if mid_ring and rho_out > 10.0:
        mid = [bm.verts.new(dir_polar(frame, p, rho_out * 0.5) * r_top) for p in phis]
        for k in range(nphi):
            k2 = (k + 1) % nphi
            bm.faces.new((center, mid[k], mid[k2]))
            bm.faces.new((mid[k], top[k], top[k2], mid[k2]))
    else:
        for k in range(nphi):
            bm.faces.new((center, top[k], top[(k + 1) % nphi]))
    cham = [bm.verts.new(dir_polar(frame, p, rho_out + c_ang) * (r_top - c)) for p in phis]
    base = [bm.verts.new(dir_polar(frame, p, rho_out + c_ang) * r_base) for p in phis]
    _close_skirt(bm, top, cham, base)


def add_ring(bm, frame, rho_in, rho_out, nphi, height):
    """Anillo (rho_in..rho_out) alrededor del eje del frame. Solido cerrado toroidal."""
    r_top = R_SPHERE + height
    r_base = R_SPHERE - BASE_SINK
    c = PLATE_CHAMFER
    c_ang = math.degrees(c / r_top)
    phis = [360.0 * k / nphi for k in range(nphi)]

    def ring(rho, r):
        return [bm.verts.new(dir_polar(frame, p, rho) * r) for p in phis]

    top_i, top_o = ring(rho_in, r_top), ring(rho_out, r_top)
    ch_i, ch_o = ring(rho_in - c_ang, r_top - c), ring(rho_out + c_ang, r_top - c)
    ba_i, ba_o = ring(rho_in - c_ang, r_base), ring(rho_out + c_ang, r_base)
    for k in range(nphi):
        k2 = (k + 1) % nphi
        bm.faces.new((top_i[k], top_o[k], top_o[k2], top_i[k2]))
        bm.faces.new((top_o[k], ch_o[k], ch_o[k2], top_o[k2]))
        bm.faces.new((ch_o[k], ba_o[k], ba_o[k2], ch_o[k2]))
        bm.faces.new((ch_i[k], top_i[k], top_i[k2], ch_i[k2]))
        bm.faces.new((ba_i[k], ch_i[k], ch_i[k2], ba_i[k2]))
        bm.faces.new((ba_o[k], ba_i[k], ba_i[k2], ba_o[k2]))


def add_cone_cutter(bm, frame, half_angle, length=1.8, n=64):
    apex = bm.verts.new((0, 0, 0))
    r = length * math.tan(rad(half_angle))
    ring = [bm.verts.new(frame[0] * length + (frame[1] * cos(rad(p)) + frame[2] * sin(rad(p))) * r)
            for p in [360.0 * k / n for k in range(n)]]
    for k in range(n):
        bm.faces.new((apex, ring[k], ring[(k + 1) % n]))
    bm.faces.new(tuple(reversed(ring)))


# --------------------------------------------------------- escena
def finish_object(bm, name, collection, material=None, smooth=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.update()
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if material:
        me.materials.append(material)
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def clay(name, gray, rough=0.6):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (gray, gray, gray, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def add_smooth_by_angle(ob, angle_deg):
    """Modificador Smooth by Angle al final de la pila (equivale al viejo Auto Smooth)."""
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    try:
        bpy.ops.object.shade_auto_smooth(angle=rad(angle_deg))
    except Exception as exc:  # fallback: cargar el node group del bundle de Blender
        print("shade_auto_smooth fallo, fallback manual:", exc)
        path = os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "geometry_nodes",
                            "smooth_by_angle.blend")
        with bpy.data.libraries.load(path) as (src, dst):
            dst.node_groups = ["Smooth by Angle"]
        mod = ob.modifiers.new("Smooth by Angle", "NODES")
        mod.node_group = bpy.data.node_groups["Smooth by Angle"]
        mod["Socket_1"] = rad(angle_deg)
    mod = ob.modifiers[-1]
    if mod.type != "NODES":
        for i, m in enumerate(ob.modifiers):
            if m.type == "NODES":
                ob.modifiers.move(i, len(ob.modifiers) - 1)
                break


def build_scene():
    scene = bpy.context.scene
    for ob in list(scene.collection.all_objects):
        bpy.data.objects.remove(ob)
    col_parts = bpy.data.collections.new("MechSphere")
    col_cut = bpy.data.collections.new("Cutters")
    col_insp = bpy.data.collections.new("Inspection")
    for c in (col_parts, col_cut, col_insp):
        scene.collection.children.link(c)

    mat_sphere = clay("Clay_Sphere", 0.22)
    mat_plate = clay("Clay_Plates", 0.50)
    mat_core = clay("Clay_Core", 0.68, 0.45)

    # esfera principal: perfecta, cerrada, sin tocar
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=SPHERE_SEGMENTS, v_segments=SPHERE_RINGS, radius=R_SPHERE)
    sphere = finish_object(bm, "Sphere_Core", col_parts, mat_sphere)

    # cono de corte alrededor del nucleo
    bm = bmesh.new()
    add_cone_cutter(bm, AXIS_FRONT, CORE_CONE_HALF)
    cutter = finish_object(bm, "Cutter_CoreCone", col_cut, smooth=False)
    cutter.display_type = "WIRE"
    cutter.hide_render = True

    la0, la1, la2 = LAT_SEAMS

    # banda ecuatorial (5 placas, frente libre para el nucleo)
    bm = bmesh.new()
    s = BAND_EQ_SEAMS
    for k in range(len(s) - 1):
        add_plate_rect(bm, s[k], s[k + 1], -la0, la0, PLATE_NLON, PLATE_NLAT["eq"], PLATE_HEIGHT)
    band_eq = finish_object(bm, "Plates_Band_Equator", col_parts, mat_plate)

    # banda superior (6 placas) -> espejo Z da la inferior
    bm = bmesh.new()
    s = BAND_UP_SEAMS + (360,)
    for k in range(len(s) - 1):
        add_plate_rect(bm, s[k], s[k + 1], la0, la1, PLATE_NLON, PLATE_NLAT["up"], PLATE_HEIGHT)
    band_up = finish_object(bm, "Plates_Band_Upper", col_parts, mat_plate)

    # casquete superior (4 sectores) -> espejo Z
    bm = bmesh.new()
    s = CAP_SEAMS + (CAP_SEAMS[0] + 360,)
    for k in range(len(s) - 1):
        add_plate_rect(bm, s[k], s[k + 1], la1, la2, PLATE_NLON, PLATE_NLAT["cap"], PLATE_HEIGHT)
    cap_up = finish_object(bm, "Plates_Cap_Upper", col_parts, mat_plate)

    # hub polar -> espejo Z
    bm = bmesh.new()
    add_disc(bm, AXIS_POLE, HUB_RHO - GROOVE_HALF, 16, HUB_HEIGHT, mid_ring=False)
    hub = finish_object(bm, "Hub_Pole_Upper", col_parts, mat_plate)

    # nucleo frontal: bisel, aro, lente
    bm = bmesh.new()
    add_ring(bm, AXIS_FRONT, CORE_BEZEL[0], CORE_BEZEL[1], CORE_SEGMENTS, CORE_BEZEL[2])
    bezel = finish_object(bm, "Core_Bezel_Outer", col_parts, mat_core)
    bm = bmesh.new()
    add_ring(bm, AXIS_FRONT, CORE_RIM[0], CORE_RIM[1], CORE_SEGMENTS, CORE_RIM[2])
    rim = finish_object(bm, "Core_Rim_Inner", col_parts, mat_core)
    bm = bmesh.new()
    add_disc(bm, AXIS_FRONT, CORE_LENS[0], CORE_SEGMENTS, CORE_LENS[1])
    lens = finish_object(bm, "Core_Lens", col_parts, mat_core)

    # modificadores (no destructivos)
    for ob in (band_eq, band_up):
        mod = ob.modifiers.new("Cut_Core", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
    for ob in (band_up, cap_up, hub):
        mod = ob.modifiers.new("Mirror_Z", "MIRROR")
        mod.use_axis = (False, False, True)
        mod.use_mirror_merge = False
    for ob in (band_eq, band_up, cap_up, hub, bezel, rim, lens):
        add_smooth_by_angle(ob, SMOOTH_ANGLE)

    parts = [sphere, band_eq, band_up, cap_up, hub, bezel, rim, lens]
    return parts, cutter, col_insp


# --------------------------------------------------------- verificacion
def evaluated_bmesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ob_eval = ob.evaluated_get(dg)
    me = ob_eval.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    ob_eval.to_mesh_clear()
    return bm


def islands(bm):
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        out.append(comp)
    return out


def signed_volume(faces):
    vol = 0.0
    for f in faces:
        vs = [v.co for v in f.verts]
        for k in range(1, len(vs) - 1):
            vol += vs[0].dot(vs[k].cross(vs[k + 1])) / 6.0
    return vol


def verify(parts, sphere):
    lines = []
    total_v = total_t = 0
    ok_all = True
    for ob in parts:
        bm = evaluated_bmesh(ob)
        nv, ne, nf = len(bm.verts), len(bm.edges), len(bm.faces)
        tris = sum(len(f.verts) - 2 for f in bm.faces)
        non_manifold_e = sum(1 for e in bm.edges if not e.is_manifold)
        boundary_e = sum(1 for e in bm.edges if e.is_boundary)
        non_manifold_v = sum(1 for v in bm.verts if not v.is_manifold)
        loose_v = sum(1 for v in bm.verts if not v.link_edges)
        loose_e = sum(1 for e in bm.edges if not e.link_faces)
        flipped = sum(1 for e in bm.edges if e.is_manifold and not e.is_contiguous)
        dup_faces = nf - len({frozenset(v.index for v in f.verts) for f in bm.faces})
        doubles = len(bmesh.ops.find_doubles(bm, verts=bm.verts, dist=1e-5)["targetmap"])
        isl = islands(bm)
        neg_vol = [len(c) for c in isl if signed_volume(c) <= 0]
        slivers = [len(c) for c in isl if sum(len(f.verts) - 2 for f in c) < 12]
        buried = sum(1 for f in bm.faces if all(v.co.length < R_SPHERE - 1e-4 for v in f.verts))
        on_surface = 0
        if ob is not sphere:
            on_surface = sum(1 for v in bm.verts if abs(v.co.length - R_SPHERE) < 1e-4)
        ok = not (non_manifold_e or boundary_e or non_manifold_v or loose_v or loose_e or flipped
                  or dup_faces or doubles or neg_vol or slivers or on_surface)
        if ob is sphere:
            euler = nv - ne + nf
            radial = max(abs(v.co.length - R_SPHERE) for v in bm.verts)
            ok = ok and euler == 2 and len(isl) == 1 and radial < 1e-5
            lines.append(f"  esfera: euler V-E+F={euler} (2 = cerrada, genero 0), "
                         f"islas={len(isl)}, desviacion radial max={radial:.2e}")
        ok_all = ok_all and ok
        total_v += nv
        total_t += tris
        lines.append(
            f"[{'OK ' if ok else 'MAL'}] {ob.name:22s} v={nv:5d} tris={tris:5d} islas={len(isl):2d} | "
            f"nonmanifold e/v={non_manifold_e}/{non_manifold_v} borde={boundary_e} "
            f"sueltos v/e={loose_v}/{loose_e} normales_invertidas={flipped} vol_neg={len(neg_vol)} "
            f"caras_dup={dup_faces} v_dobles={doubles} astillas={slivers} "
            f"caras_enterradas={buried} v_en_superficie={on_surface}")
        bm.free()
    lines.append(f"TOTAL evaluado: vertices={total_v} triangulos={total_t}")
    lines.append("RESULTADO: " + ("TODO OK" if ok_all else "HAY PROBLEMAS"))
    return lines, ok_all, total_v, total_t


def glb_counts(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, version, length = struct.unpack_from("<III", data, 0)
    clen, ctype = struct.unpack_from("<II", data, 12)
    doc = json.loads(data[20:20 + clen].decode("utf-8"))
    acc = doc["accessors"]
    tris = verts = 0
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            tris += acc[prim["indices"]]["count"] // 3
            verts += acc[prim["attributes"]["POSITION"]]["count"]
    return len(doc["meshes"]), verts, tris, os.path.getsize(path)


# --------------------------------------------------------- render
def setup_render(scene, col_insp):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = RENDER_RES
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = RENDER_SAMPLES
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    world = bpy.data.worlds.new("Inspection_World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.30, 0.30, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    scene.world = world

    def light(name, kind, energy, loc, target=Vector((0, 0, 0)), size=None):
        li = bpy.data.lights.new(name, kind)
        li.energy = energy
        if size:
            li.size = size
        ob = bpy.data.objects.new(name, li)
        ob.location = loc
        ob.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        col_insp.objects.link(ob)
        return ob

    light("Light_Key", "SUN", 2.5, (-3, -4, 5))
    light("Light_Fill", "AREA", 200, (5, -2, 2), size=4)
    light("Light_Rim", "AREA", 120, (2, 5, 3), size=4)

    cams = {}
    r = 8.0

    def cam(name, loc, rot=None, ortho=True):
        cd = bpy.data.cameras.new(name)
        if ortho:
            cd.type = "ORTHO"
            cd.ortho_scale = 2.5
        else:
            cd.lens = 60
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        if rot is not None:
            ob.rotation_euler = rot
        else:
            ob.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        col_insp.objects.link(ob)
        cams[name] = ob

    cam("Cam_Front", (0, -r, 0), (rad(90), 0, 0))
    cam("Cam_Back", (0, r, 0), (rad(90), 0, rad(180)))
    cam("Cam_Right", (r, 0, 0), (rad(90), 0, rad(90)))
    cam("Cam_Left", (-r, 0, 0), (rad(90), 0, rad(-90)))
    cam("Cam_Top", (0, 0, r), (0, 0, 0))
    cam("Cam_ThreeQuarter", (-3.2, -3.4, 2.6), ortho=False)
    return cams


def render_all(scene, cams, out_dir):
    names = ["Cam_Front", "Cam_Back", "Cam_Left", "Cam_Right", "Cam_Top", "Cam_ThreeQuarter"]
    files = []
    for n in names:
        scene.camera = cams[n]
        fn = n[4:].lower().replace("threequarter", "three-quarter") + ".png"
        scene.render.filepath = os.path.join(out_dir, fn)
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    return files


def contact_sheet(files, out_path, cell=512):
    import numpy as np
    cols, rows = 3, 2
    sheet = np.zeros((rows * cell, cols * cell, 4), dtype=np.float32)
    for idx, path in enumerate(files):
        img = bpy.data.images.load(path)
        img.scale(cell, cell)
        px = np.empty(cell * cell * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(cell, cell, 4)
        cx, cy = idx % cols, idx // cols
        y0 = (rows - 1 - cy) * cell   # fila 0 de pixels = abajo
        sheet[y0:y0 + cell, cx * cell:(cx + 1) * cell] = px
        bpy.data.images.remove(img)
    out = bpy.data.images.new("contact_sheet", cols * cell, rows * cell, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = out_path
    out.file_format = "PNG"
    out.save()


# --------------------------------------------------------- main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = os.path.abspath(argv[0] if argv else "esfera-mecanica-out")
    renders = os.path.join(out_dir, "renders")
    os.makedirs(renders, exist_ok=True)

    parts, cutter, col_insp = build_scene()
    sphere = parts[0]
    scene = bpy.context.scene

    lines, ok, tv, tt = verify(parts, sphere)
    print("\n".join(lines))

    cams = setup_render(scene, col_insp)
    blend = os.path.join(out_dir, "esfera-mecanica.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)

    glb = os.path.join(out_dir, "esfera-mecanica.glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(o in parts)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_materials="EXPORT",
                              export_animations=False, export_skins=False)
    nmesh, gv, gt, size = glb_counts(glb)
    lines.append(f"GLB: mallas={nmesh} vertices={gv} triangulos={gt} bytes={size}")

    files = render_all(scene, cams, renders)
    contact_sheet(files, os.path.join(renders, "contact-sheet.png"))

    with open(os.path.join(out_dir, "reporte.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines[-2:]))
    print("SALIDA:", out_dir)


if __name__ == "__main__":
    main()
