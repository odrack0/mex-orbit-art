"""Reproyecta las texturas que Meshy pinto sobre SU despliegue a NUESTRA malla, UVs y materiales.

Uso:
    blender --background --factory-startup --python tools/reproyectar-texturas.py -- \
        source/3d-models/procedural/esfera-mecanica  source/3d-models/crudo/esfera-mecanica-v2-meshy.glb

Malla autoritativa: <carpeta>/esfera-mecanica-v2-uv.blend (+ .glb). El GLB de Meshy solo aporta
apariencia: base color, metallic/roughness y normal. Meshy conserva la geometria vertice a vertice
(solo la reescala a caja unidad y retriangula los n-gonos), asi que la correspondencia es exacta:
cada texel nuestro -> punto 3D -> triangulo gemelo de Meshy -> UV de Meshy -> muestreo bilineal.

Salida en <carpeta>:
    textures/{basecolor,metallic,roughness,normal,orm}.png   2048, mas textures/1024/
    esfera-mecanica-v3-tex.blend / .glb                       nuestras 8 piezas y 3 materiales, texturizadas
    renders/reproj-*.png, renders/compare-*.png               validacion y comparativas con el GLB de Meshy
    reporte-reproyeccion.txt

Diales:
"""
import importlib.util
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector, kdtree
from mathutils.bvhtree import BVHTree

# ----------------------------------------------------------------- diales
TEX_SIZE = 2048
SUPERSAMPLE = 2          # muestras por lado y texel (2 -> 4 muestras + bilineal en origen)
TWIN_EPS = 1e-5          # distancia entre centroides para dar dos triangulos por gemelos
PAD_FULL = True          # relleno "infinito": todo texel sin cobertura toma el color de la isla mas cercana
RENDER_RES = 1024
MIP_RES = 256            # "simulacion de mipmap": render al tamano de juego
RENDER_SAMPLES = 32
# ------------------------------------------------------------------------


def load_builder():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("esfera_mecanica", os.path.join(here, "esfera-mecanica.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lines = []


def log(s):
    print(s)
    lines.append(s)


# --------------------------------------------------------- color
def srgb_to_lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


# --------------------------------------------------------- imagenes
def image_to_np(img):
    w, h = img.size
    buf = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(buf)
    return buf.reshape(h, w, img.channels)[:, :, :3].copy()   # fila 0 = abajo (v = 0)


def save_png(path, rgb, colorspace):
    h, w = rgb.shape[:2]
    if rgb.ndim == 2:
        rgb = np.repeat(rgb[:, :, None], 3, axis=2)
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=False)
    img.colorspace_settings.name = colorspace
    px = np.concatenate([rgb.astype(np.float32), np.ones((h, w, 1), np.float32)], axis=2)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def sample_bilinear(img, uv):
    H, W = img.shape[:2]
    x = np.clip(uv[:, 0] * W - 0.5, 0, W - 1)
    y = np.clip(uv[:, 1] * H - 0.5, 0, H - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, W - 1)
    y1 = np.minimum(y0 + 1, H - 1)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def box_down(a, f):
    h, w = a.shape[:2]
    return a.reshape(h // f, f, w // f, f, -1).mean(axis=(1, 3))


def shifted(a, dy, dx, fill):
    H, W = a.shape
    out = np.full_like(a, fill)
    out[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] = a[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)]
    return out


def nearest_valid(valid):
    """Jump flooding: para cada texel, indice (y, x) del texel valido mas cercano."""
    H, W = valid.shape
    Y, X = np.mgrid[0:H, 0:W]
    by = np.where(valid, Y, -1).astype(np.int32)
    bx = np.where(valid, X, -1).astype(np.int32)
    INF = np.int64(1 << 40)

    def dist(cy, cx):
        d = (Y - cy).astype(np.int64) ** 2 + (X - cx).astype(np.int64) ** 2
        return np.where(cy < 0, INF, d)

    best = dist(by, bx)
    step = 1
    while step * 2 < max(H, W):
        step *= 2
    steps = []
    while step >= 1:
        steps.append(step)
        step //= 2
    steps.append(1)
    for s in steps:
        for dy in (-s, 0, s):
            for dx in (-s, 0, s):
                if dy == 0 and dx == 0:
                    continue
                cy = shifted(by, dy, dx, -1)
                cx = shifted(bx, dy, dx, -1)
                d = dist(cy, cx)
                better = d < best
                by = np.where(better, cy, by)
                bx = np.where(better, cx, bx)
                best = np.where(better, d, best)
    return by, bx


# --------------------------------------------------------- mallas
def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def tri_data(objs):
    """Por triangulo: posiciones (3,3), uv (3,2), tangente (3,3), signo bitangente (3,), normal (3,3), material."""
    P, UV, T, BS, N, M = [], [], [], [], [], []
    for ob in objs:
        me = ob.data
        # MikkTSpace solo acepta tris/quads: triangular la copia de trabajo (misma triangulacion que el exportador)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(me)
        bm.free()
        me.calc_loop_triangles()
        me.calc_tangents()
        assert any(l.tangent.length > 0.5 for l in me.loops), f"{ob.name}: sin tangentes"
        mw = ob.matrix_world
        uv = me.uv_layers.active.uv
        for lt in me.loop_triangles:
            ls = lt.loops
            P.append([(mw @ me.vertices[me.loops[l].vertex_index].co)[:] for l in ls])
            UV.append([uv[l].vector[:] for l in ls])
            T.append([me.loops[l].tangent[:] for l in ls])
            BS.append([me.loops[l].bitangent_sign for l in ls])
            N.append([me.loops[l].normal[:] for l in ls])
            M.append(me.materials[me.polygons[lt.polygon_index].material_index].name if me.materials else "")
    return (np.array(P, np.float64), np.array(UV, np.float64), np.array(T, np.float64),
            np.array(BS, np.float64), np.array(N, np.float64), M)


def normalize(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def bary_in_tri(p, tri):
    """p (n,3), tri (n,3,3) -> coordenadas baricentricas (n,3)."""
    v0 = tri[:, 1] - tri[:, 0]
    v1 = tri[:, 2] - tri[:, 0]
    v2 = p - tri[:, 0]
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-18)
    b1 = (d11 * d20 - d01 * d21) / den
    b2 = (d00 * d21 - d01 * d20) / den
    return np.stack([1 - b1 - b2, b1, b2], axis=1)


# --------------------------------------------------------- reproyeccion
def reproject(ours, meshy, tex_base_lin, tex_mr, tex_nrm):
    Po, UVo, To, BSo, No, Mo = tri_data(ours)
    Pm, UVm, Tm, BSm, Nm, _ = tri_data(meshy)

    # Meshy normaliza la caja: deshacer escala y centrado
    ext_o = Po.reshape(-1, 3).max(0) - Po.reshape(-1, 3).min(0)
    ext_m = Pm.reshape(-1, 3).max(0) - Pm.reshape(-1, 3).min(0)
    s = float((ext_m / ext_o).mean())
    t = (Pm.reshape(-1, 3).max(0) + Pm.reshape(-1, 3).min(0)) / 2 - s * (Po.reshape(-1, 3).max(0) + Po.reshape(-1, 3).min(0)) / 2
    Pm = (Pm - t) / s
    log(f"alineacion Meshy -> nuestra: escala {s:.5f}, traslacion {t.round(5)}")

    # gemelos por centroide + permutacion de vertices
    cm = Pm.mean(1)
    kd = kdtree.KDTree(len(cm))
    for i, c in enumerate(cm):
        kd.insert(Vector(c), i)
    kd.balance()
    twin = np.full(len(Po), -1, np.int64)
    perm = np.zeros((len(Po), 3), np.int64)
    for i, tri in enumerate(Po):
        _, j, d = kd.find(Vector(tri.mean(0)))
        if d < TWIN_EPS:
            twin[i] = j
            for k in range(3):
                perm[i, k] = int(np.argmin(np.linalg.norm(Pm[j] - tri[k], axis=1)))
    log(f"triangulos nuestros={len(Po)} con gemelo exacto={int((twin >= 0).sum())} "
        f"resueltos por BVH (n-gonos retriangulados)={int((twin < 0).sum())}")
    bvh = BVHTree.FromPolygons([tuple(v) for v in Pm.reshape(-1, 3)],
                               [(3 * j, 3 * j + 1, 3 * j + 2) for j in range(len(Pm))])

    S = TEX_SIZE * SUPERSAMPLE
    acc_base = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float64)
    acc_mr = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float64)
    acc_n = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float64)
    count = np.zeros((TEX_SIZE, TEX_SIZE), np.float64)
    n_samples = 0
    max_bvh_dist = 0.0

    for i in range(len(Po)):
        p = UVo[i] * S
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, S - 1), min(y1, S - 1)
        if x1 < x0 or y1 < y0:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = p
        det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(det) < 1e-12:
            continue
        l1 = ((bx - X) * (cy - Y) - (cx - X) * (by - Y)) / det
        l2 = ((cx - X) * (ay - Y) - (ax - X) * (cy - Y)) / det
        l3 = 1.0 - l1 - l2
        eps = -1e-6
        inside = (l1 > eps) & (l2 > eps) & (l3 > eps)
        if not inside.any():
            continue
        bary = np.stack([l1[inside], l2[inside], l3[inside]], axis=1)
        xs = X[inside].astype(int)
        ys = Y[inside].astype(int)
        n = len(bary)
        n_samples += n

        pts = bary @ Po[i]                                   # (n,3) puntos 3D
        if twin[i] >= 0:
            j = np.full(n, twin[i], np.int64)
            bary_m = np.zeros_like(bary)
            for k in range(3):
                bary_m[:, perm[i, k]] = bary[:, k]
        else:
            j = np.empty(n, np.int64)
            for q, pt in enumerate(pts):
                loc, _, idx, d = bvh.find_nearest(Vector(pt))
                j[q] = idx
                max_bvh_dist = max(max_bvh_dist, d)
            bary_m = np.clip(bary_in_tri(pts, Pm[j]), 0, 1)
            bary_m /= bary_m.sum(1, keepdims=True)

        uv_m = np.einsum("nk,nkd->nd", bary_m, UVm[j])
        base = sample_bilinear(tex_base_lin, uv_m)
        mr = sample_bilinear(tex_mr, uv_m)
        nts = sample_bilinear(tex_nrm, uv_m) * 2.0 - 1.0     # tangent space de Meshy

        # Re-base entre bases tangentes: solo la rotacion en el plano tangente (x, y); z se conserva.
        # Meshy suaviza sus normales de vertice a traves de las aristas duras (media 21 grados
        # respecto a la cara), asi que NO se pasa por la normal en mundo: eso copiaria su
        # suavizado dentro del mapa y anularia nuestro Smooth by Angle. Un normal plano de
        # Meshy queda plano sobre nuestra geometria; el detalle relativo se conserva.
        Tm_ = normalize(np.einsum("nk,nkd->nd", bary_m, Tm[j]))
        Nm_ = normalize(np.einsum("nk,nkd->nd", bary_m, Nm[j]))
        Bm_ = np.cross(Nm_, Tm_) * BSm[j][:, 0:1]
        To_ = normalize(bary @ To[i])
        No_ = normalize(bary @ No[i])
        Bo_ = np.cross(No_, To_) * BSo[i][0]
        x, y, z = nts[:, 0:1], nts[:, 1:2], nts[:, 2:3]
        tt = (Tm_ * To_).sum(1, keepdims=True); bt = (Bm_ * To_).sum(1, keepdims=True)
        tb = (Tm_ * Bo_).sum(1, keepdims=True); bb = (Bm_ * Bo_).sum(1, keepdims=True)
        n_ours = np.concatenate([x * tt + y * bt, x * tb + y * bb, z], axis=1)

        tx = xs // SUPERSAMPLE
        ty = ys // SUPERSAMPLE
        np.add.at(acc_base, (ty, tx), base)
        np.add.at(acc_mr, (ty, tx), mr)
        np.add.at(acc_n, (ty, tx), n_ours)
        np.add.at(count, (ty, tx), 1.0)

    valid = count > 0
    log(f"muestras={n_samples} texeles cubiertos={int(valid.sum())} ({valid.mean()*100:.1f}%)  "
        f"distancia max punto->malla Meshy en los no gemelos={max_bvh_dist:.2e}")
    c = np.maximum(count, 1)[:, :, None]
    base = acc_base / c
    mr = acc_mr / c
    nrm = normalize(acc_n / c)
    nrm[~valid] = (0, 0, 1)

    # padding: cada texel vacio toma el valor del texel cubierto mas cercano (islas separadas -> corte a mitad)
    by, bx = nearest_valid(valid)
    base = base[by, bx]
    mr = mr[by, bx]
    nrm = nrm[by, bx]
    return base, mr, nrm, valid


def write_textures(out_dir, base_lin, mr, nrm, valid):
    tex = os.path.join(out_dir, "textures")
    os.makedirs(os.path.join(tex, "1024"), exist_ok=True)
    nrm01 = np.clip(nrm * 0.5 + 0.5, 0, 1)
    orm = np.stack([mr[:, :, 0], mr[:, :, 1], mr[:, :, 2]], axis=2)
    sets = {"2048": (base_lin, orm, nrm01)}
    b2 = box_down(base_lin, 2)
    o2 = box_down(orm, 2)
    n2 = normalize(box_down(nrm, 2)) * 0.5 + 0.5
    sets["1024"] = (b2, o2, n2)
    for size, (b, o, n) in sets.items():
        d = tex if size == "2048" else os.path.join(tex, size)
        save_png(os.path.join(d, "basecolor.png"), lin_to_srgb(b), "sRGB")
        save_png(os.path.join(d, "orm.png"), np.clip(o, 0, 1), "Non-Color")
        save_png(os.path.join(d, "roughness.png"), np.clip(o[:, :, 1], 0, 1), "Non-Color")
        save_png(os.path.join(d, "metallic.png"), np.clip(o[:, :, 2], 0, 1), "Non-Color")
        save_png(os.path.join(d, "normal.png"), np.clip(n, 0, 1), "Non-Color")
    save_png(os.path.join(tex, "coverage.png"), valid.astype(np.float32), "Non-Color")
    log(f"texturas: 2048 y 1024 en {tex}  (basecolor sRGB; orm/roughness/metallic/normal Non-Color; "
        f"orm: G=roughness B=metallic, R tal cual de Meshy)")


# --------------------------------------------------------- materiales
def build_material(mat, tex_dir, mask_path=None):
    mat.use_backface_culling = True   # glTF singleSided: game-ready
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])

    def tex(name, cs, y):
        node = nt.nodes.new("ShaderNodeTexImage")
        path = os.path.join(tex_dir, name)
        img = bpy.data.images.get(name) or bpy.data.images.load(path)
        img.colorspace_settings.name = cs
        node.image = img
        node.location = (-700, y)
        return node

    b = tex("basecolor.png", "sRGB", 300)
    nt.links.new(b.outputs["Color"], bsdf.inputs["Base Color"])
    o = tex("orm.png", "Non-Color", 0)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-400, 0)
    nt.links.new(o.outputs["Color"], sep.inputs[0])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    n = tex("normal.png", "Non-Color", -300)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (-400, -300)
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if mask_path:
        m = nt.nodes.new("ShaderNodeTexImage")
        m.image = bpy.data.images.get("emission-mask.png") or bpy.data.images.load(mask_path)
        m.image.colorspace_settings.name = "Non-Color"
        m.location = (-700, -600)
        nt.links.new(m.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 0.0   # apagado: el cyan llega en la fase siguiente
    return bsdf


# --------------------------------------------------------- render
def render(scene, cam, path, res):
    scene.camera = bpy.data.objects[cam]
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def load_png_np(path):
    img = bpy.data.images.load(path)
    a = image_to_np(img)
    bpy.data.images.remove(img)
    return a


def main():
    builder = load_builder()
    argv = sys.argv[sys.argv.index("--") + 1:]
    out_dir = os.path.abspath(argv[0])
    meshy_path = os.path.abspath(argv[1])
    ours_glb = os.path.join(out_dir, "esfera-mecanica-v2-uv.glb")
    ours_blend = os.path.join(out_dir, "esfera-mecanica-v2-uv.blend")
    renders = os.path.join(out_dir, "renders")
    if not os.path.isfile(ours_glb) or not os.path.isfile(ours_blend):
        raise FileNotFoundError("faltan los artefactos UV autoritativos v2 en la carpeta de salida")
    if not os.path.isfile(meshy_path):
        raise FileNotFoundError(f"no existe la fuente de apariencia Meshy: {meshy_path}")
    _, expected_vertices, expected_triangles, _ = builder.glb_counts(ours_glb)

    # 1) datos de ambas mallas en una escena vacia
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ours = import_glb(ours_glb)
    meshy = import_glb(meshy_path)
    imgs = {i.name.lower(): i for i in bpy.data.images}
    base_img = next(v for k, v in imgs.items() if "base" in k)
    mr_img = next(v for k, v in imgs.items() if "metallic" in k)
    nrm_img = next(v for k, v in imgs.items() if "normal" in k)
    log(f"Meshy: {len(meshy)} malla(s), texturas {base_img.size[0]}x{base_img.size[1]} "
        f"base={base_img.name} mr={mr_img.name} normal={nrm_img.name}")
    tex_base_lin = srgb_to_lin(image_to_np(base_img))
    tex_mr = image_to_np(mr_img)
    tex_nrm = image_to_np(nrm_img)

    base, mr, nrm, valid = reproject(ours, meshy, tex_base_lin, tex_mr, tex_nrm)
    write_textures(out_dir, base, mr, nrm, valid)

    # 2) v3: nuestro .blend con los materiales texturizados
    bpy.ops.wm.open_mainfile(filepath=ours_blend)
    tex_dir = os.path.join(out_dir, "textures")
    for name in ("MAT_HULL", "MAT_RECESSES", "MAT_EMISSION"):
        build_material(bpy.data.materials[name], tex_dir,
                       mask_path=os.path.join(out_dir, "emission-mask.png") if name == "MAT_EMISSION" else None)
    parts = sorted([o for o in bpy.data.collections["MechSphere"].objects if o.type == "MESH"], key=lambda o: o.name)
    for img in bpy.data.images:
        if img.filepath:
            img.filepath = bpy.path.relpath(img.filepath)
    v3_blend = os.path.join(out_dir, "esfera-mecanica-v3-tex.blend")
    bpy.ops.wm.save_as_mainfile(filepath=v3_blend)
    v3_glb = os.path.join(out_dir, "esfera-mecanica-v3-tex.glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(o in parts)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.gltf(filepath=v3_glb, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_texcoords=True,
                              export_normals=True, export_image_format="AUTO",   # sin tangentes: Godot las genera (MikkTSpace) igual en las 8 piezas
                              export_animations=False, export_skins=False)
    nmesh, gv, gt, size = builder.glb_counts(v3_glb)
    log(f"GLB v3: mallas={nmesh} vertices={gv} triangulos={gt} bytes={size}")

    # 3) geometria identica a la aprobada
    vlines, ok, tv, tt = builder.verify(parts, bpy.data.objects["Sphere_Core"])
    lines.extend(vlines[-2:])
    geometry_identical = tt == expected_triangles and ok
    lines.append(
        f"geometria: {tt} triangulos evaluados "
        f"(master UV: {expected_triangles}; vertices GLB almacenados: {expected_vertices}) -> "
        f"{'IDENTICA' if geometry_identical else 'REVISAR'}"
    )
    mats = {o.name: [s.material.name for s in o.material_slots] for o in parts}
    lines.append(f"materiales por pieza: {mats}")

    # 4) renders nuestros
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = RENDER_SAMPLES
    scene.view_settings.view_transform = "Standard"
    views = (("Cam_ThreeQuarter", "three-quarter"), ("Cam_Top", "top"), ("Cam_Front", "front"))
    for cam, name in views:
        render(scene, cam, os.path.join(renders, f"reproj-{name}.png"), RENDER_RES)
    for cam, name in views[:2]:
        render(scene, cam, os.path.join(renders, f"reproj-{name}-{MIP_RES}px.png"), MIP_RES)
    # 1024: las mismas texturas a la mitad, para comparar
    for img in bpy.data.images:
        if img.filepath and "textures" in img.filepath and "1024" not in img.filepath:
            img.filepath = img.filepath.replace("textures" + os.sep, "textures" + os.sep + "1024" + os.sep).replace("textures/", "textures/1024/")
            img.reload()
    render(scene, "Cam_ThreeQuarter", os.path.join(renders, f"reproj-three-quarter-tex1024.png"), RENDER_RES)
    render(scene, "Cam_Top", os.path.join(renders, f"reproj-top-tex1024-{MIP_RES}px.png"), MIP_RES)
    for img in bpy.data.images:
        if img.filepath and "1024" in img.filepath:
            img.filepath = img.filepath.replace("1024" + os.sep, "").replace("1024/", "")
            img.reload()
    # chequeo de emision (temporal, no se guarda): la lente emite blanco neutro, nada mas cambia
    bsdf = bpy.data.materials["MAT_EMISSION"].node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Emission Strength"].default_value = 3.0
    render(scene, "Cam_ThreeQuarter", os.path.join(renders, "reproj-emission-check.png"), RENDER_RES)
    bsdf.inputs["Emission Strength"].default_value = 0.0

    # 5) el GLB de Meshy, alineado a nuestro tamano, con las mismas camaras y luces
    for o in parts:
        o.hide_render = True
    mobjs = import_glb(meshy_path)
    Po = np.array([(o.matrix_world @ v.co)[:] for o in parts for v in o.data.vertices])
    Pm = np.array([(o.matrix_world @ v.co)[:] for o in mobjs for v in o.data.vertices])
    s = float(((Pm.max(0) - Pm.min(0)) / (Po.max(0) - Po.min(0))).mean())
    t = (Pm.max(0) + Pm.min(0)) / 2 - s * (Po.max(0) + Po.min(0)) / 2
    for o in mobjs:
        o.scale = (1 / s,) * 3
        o.location = tuple(-t / s)
    for cam, name in views:
        render(scene, cam, os.path.join(renders, f"meshy-{name}.png"), RENDER_RES)
    for cam, name in views[:2]:
        render(scene, cam, os.path.join(renders, f"meshy-{name}-{MIP_RES}px.png"), MIP_RES)
    for o in mobjs:
        bpy.data.objects.remove(o)
    for o in parts:
        o.hide_render = False

    # 6) comparativas: [Meshy | reproyectado | diferencia x4]
    for cam, name in views:
        a = load_png_np(os.path.join(renders, f"meshy-{name}.png"))
        b = load_png_np(os.path.join(renders, f"reproj-{name}.png"))
        d = np.abs(a - b)
        sheet = np.concatenate([a, b, np.clip(d * 4, 0, 1)], axis=1)
        save_png(os.path.join(renders, f"compare-{name}.png"), sheet, "sRGB")
        log(f"comparativa {name}: diferencia media={d.mean():.4f} p99={np.percentile(d, 99):.4f} "
            f"max={d.max():.3f} (0..1 sRGB; incluye el ruido de muestreo del render)")
    for name in ("three-quarter", "top"):
        a = load_png_np(os.path.join(renders, f"meshy-{name}-{MIP_RES}px.png"))
        b = load_png_np(os.path.join(renders, f"reproj-{name}-{MIP_RES}px.png"))
        c = load_png_np(os.path.join(renders, f"reproj-{name}-tex1024-{MIP_RES}px.png")) if name == "top" else b
        sheet = np.concatenate([a, b, c], axis=1)
        save_png(os.path.join(renders, f"compare-{name}-{MIP_RES}px.png"), sheet, "sRGB")
        log(f"mip {MIP_RES}px {name}: diferencia media Meshy vs reproyectado={np.abs(a - b).mean():.4f}")

    with open(os.path.join(out_dir, "reporte-reproyeccion.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
