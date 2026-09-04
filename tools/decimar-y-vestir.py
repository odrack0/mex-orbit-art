# Saca la MALLA DEL JUEGO del ALTO de Meshy y la viste con la textura del REMESH.
# Es el paso que sustituye al remesh como malla (3-sep-2026): medido en el ACI-03,
# un Decimate de Blender desde el alto conserva juntas, filos y puas que el remesh
# de Meshy derrite con los mismos triangulos, y ademas no abre agujeros. El remesh
# queda como LIENZO: es donde Meshy pinta, y de ahi se traspasa la pintura por
# horneado "selected to active" a la malla decimada.
#
#   blender --background --factory-startup --python tools/decimar-y-vestir.py -- \
#       <alto.glb> <remesh_texturizado.glb> <salida.glb> [tris=100000] [lado=2048] [distancia=0.08]
#
# - `alto`: el generado de Meshy SIN textura (1,5-3 M de tris), en crudo/alto/.
# - `remesh_texturizado`: el remesh adaptativo Ultra (~100 k) CON textura, en crudo/.
#   Los dos del mismo generado: comparten espacio, y el bake lanza rayos de uno a otro.
# - `tris`: presupuesto de la malla del juego. 100 k es el punto medido (30 bichos de
#   150 k dan los mismos fps que 30 de 56 k en la iGPU; el LOD de Godot hace el resto).
# - `lado`: tamanio de las texturas traspasadas (color base y metallic-roughness).
# - `distancia`: jaula del bake en unidades del modelo; el remesh Ultra sigue al alto
#   de cerca y 0,08 sobra. Si salen manchas negras, subirla; si sangra entre partes
#   vecinas, bajarla.
#
# Sale la malla decimada con UV automaticas (por angulo), color base y
# metallic-roughness traspasados y un Principled BSDF listo para
# hornear-normales.py (que pone el relieve del alto) y despues normalize-model.py.
import bpy, os, sys, math, time
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
if len(args) < 3:
    sys.exit("uso: decimar-y-vestir.py <alto.glb> <remesh_tex.glb> <salida.glb> [tris] [lado] [distancia]")
alto_p, remesh_p, salida = os.path.abspath(args[0]), os.path.abspath(args[1]), os.path.abspath(args[2])
TRIS = int(args[3]) if len(args) > 3 else 100000
LADO = int(args[4]) if len(args) > 4 else 2048
DIST = float(args[5]) if len(args) > 5 else 0.08
t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
esc = bpy.context.scene


def importar(ruta, nombre):
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=ruta)
    nuevos = [o for o in bpy.data.objects if o not in antes and o.type == "MESH"]
    if not nuevos:
        sys.exit("RECHAZAR: %s no trae mallas" % ruta)
    # el export de Meshy a veces trae un cubo suelto de 12 tris: una malla
    # parasita que, unida al remesh, se pondria en el camino de los rayos del bake
    mayor = max(len(o.data.polygons) for o in nuevos)
    for o in [o for o in nuevos if len(o.data.polygons) < mayor * 0.01]:
        print("descartada malla parasita '%s' (%d caras)" % (o.name, len(o.data.polygons)))
        bpy.data.objects.remove(o, do_unlink=True)
    nuevos = [o for o in nuevos if o.name in bpy.data.objects]
    for o in bpy.data.objects:
        o.select_set(False)
    for o in nuevos:
        o.select_set(True)
    bpy.context.view_layer.objects.active = nuevos[0]
    if len(nuevos) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = nombre
    # Blender headless no evalua el depsgraph: las transformaciones van a la malla
    obj.data.transform(obj.matrix_world)
    obj.matrix_world.identity()
    for o in [o for o in bpy.data.objects if o not in antes and o.type != "MESH"]:
        bpy.data.objects.remove(o, do_unlink=True)
    obj.select_set(False)
    return obj


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def imagen_de(mat, socket):
    """La imagen que alimenta un socket del Principled (directo o via Separate Color)."""
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return None
    vistos, cola = set(), [l.from_node for l in mat.node_tree.links if l.to_node == bsdf and l.to_socket.name == socket]
    while cola:
        n = cola.pop()
        if n in vistos:
            continue
        vistos.add(n)
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image
        cola += [l.from_node for l in mat.node_tree.links if l.to_node == n]
    return None


alto = importar(alto_p, "alto")
fuente = importar(remesh_p, "fuente")
n_alto = tris(alto)
print("alto %d tris · remesh %d tris" % (n_alto, tris(fuente)))
if not fuente.data.materials or not fuente.data.uv_layers:
    sys.exit("RECHAZAR: el remesh no trae material o UV — no hay pintura que traspasar")
mat_f = fuente.data.materials[0]
img_color = imagen_de(mat_f, "Base Color")
img_mr = imagen_de(mat_f, "Roughness") or imagen_de(mat_f, "Metallic")
if img_color is None:
    sys.exit("RECHAZAR: el remesh no trae textura de color base")
print("texturas del remesh: color %dx%d · metallic-roughness %s" % (
    img_color.size[0], img_color.size[1], "%dx%d" % tuple(img_mr.size) if img_mr else "NO"))

# 1. la malla del juego: Decimate (collapse) del alto al presupuesto
juego = alto
mod = juego.modifiers.new("dec", "DECIMATE")
mod.decimate_type = "COLLAPSE"
mod.ratio = TRIS / max(n_alto, 1)
bpy.context.view_layer.objects.active = juego
bpy.ops.object.modifier_apply(modifier="dec")
juego.name = "juego"
print("decimado a %d tris (%.0f s)" % (tris(juego), time.time() - t0))

# 2. UV automaticas por angulo: la textura traspasada vive en estas islas
while juego.data.uv_layers:
    juego.data.uv_layers.remove(juego.data.uv_layers[0])
for o in bpy.data.objects:
    o.select_set(o is juego)
bpy.context.view_layer.objects.active = juego
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.002)
bpy.ops.object.mode_set(mode="OBJECT")
print("UV automaticas (%.0f s)" % (time.time() - t0))

# 3. material del juego con las imagenes destino
mat = bpy.data.materials.new("juego_mat")
mat.use_nodes = True
nodos, links = mat.node_tree.nodes, mat.node_tree.links
bsdf = next(n for n in nodos if n.type == "BSDF_PRINCIPLED")
img_c = bpy.data.images.new("base_color", LADO, LADO, alpha=False)
img_c.colorspace_settings.name = "sRGB"
nodo_c = nodos.new("ShaderNodeTexImage"); nodo_c.image = img_c
links.new(nodo_c.outputs["Color"], bsdf.inputs["Base Color"])
juego.data.materials.clear()
juego.data.materials.append(mat)

esc.render.engine = "CYCLES"
esc.cycles.device = "CPU"
esc.cycles.samples = 4
b = esc.render.bake
b.use_selected_to_active = True
b.cage_extrusion = DIST
b.max_ray_distance = DIST * 2
b.margin = 12
b.use_clear = True


def hornear(tipo, nodo_destino):
    for n in nodos:
        n.select = False
    nodo_destino.select = True
    nodos.active = nodo_destino
    for o in bpy.data.objects:
        o.select_set(o is fuente or o is juego)
    bpy.context.view_layer.objects.active = juego
    bpy.ops.object.bake(type=tipo)


# 3a. color base: solo el pase de color del difuso (sin luz)
b.use_pass_direct = False; b.use_pass_indirect = False; b.use_pass_color = True
hornear("DIFFUSE", nodo_c)
px = np.array(img_c.pixels[:]).reshape(-1, 4)[:, :3]
negros = float((px.max(axis=1) < 0.01).mean())
print("color traspasado (%.0f s) · pixeles sin color: %.1f %%" % (time.time() - t0, negros * 100))
if negros > 0.5:
    sys.exit("RECHAZAR: mas de la mitad de la textura salio negra — el remesh y el alto no comparten espacio o la distancia es corta")

# 3b. metallic-roughness: la imagen del remesh se emite tal cual y se hornea como EMIT
if img_mr is not None:
    img_m = bpy.data.images.new("metallic_roughness", LADO, LADO, alpha=False)
    img_m.colorspace_settings.name = "Non-Color"
    nodo_m = nodos.new("ShaderNodeTexImage"); nodo_m.image = img_m
    sep = nodos.new("ShaderNodeSeparateColor")
    links.new(nodo_m.outputs["Color"], sep.inputs["Color"])
    links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    # la fuente pasa a emitir su mapa MR (el material original ya no hace falta)
    nf, lf = mat_f.node_tree.nodes, mat_f.node_tree.links
    salida_f = next(n for n in nf if n.type == "OUTPUT_MATERIAL")
    emi = nf.new("ShaderNodeEmission")
    tex_mr = nf.new("ShaderNodeTexImage"); tex_mr.image = img_mr
    img_mr.colorspace_settings.name = "Non-Color"
    lf.new(tex_mr.outputs["Color"], emi.inputs["Color"])
    for l in list(lf):
        if l.to_node == salida_f and l.to_socket.name == "Surface":
            lf.remove(l)
    lf.new(emi.outputs["Emission"], salida_f.inputs["Surface"])
    hornear("EMIT", nodo_m)
    img_m.pack()
    print("metallic-roughness traspasado (%.0f s)" % (time.time() - t0))
img_c.pack()

# 4. sale solo la malla del juego
bpy.data.objects.remove(fuente, do_unlink=True)
os.makedirs(os.path.dirname(salida), exist_ok=True)
for o in bpy.data.objects:
    o.select_set(o is juego)
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=True,
                          export_yup=True, use_selection=True, export_image_format="AUTO")
print("escrito %s (%.1f MB) · %d tris · texturas %dx%d" % (
    salida, os.path.getsize(salida) / 1048576.0, tris(juego), LADO, LADO))
