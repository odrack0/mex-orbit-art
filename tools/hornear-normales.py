# Hornea el relieve de un modelo ALTO (el crudo de Meshy a 100 k) sobre un
# modelo BAJO (su remesh a 10-20 k) como mapa de normales en espacio tangente:
# el juego dibuja la malla barata y la luz dibuja el detalle del caro. Es el
# paso 3 del flujo clasico (retopologia -> silueta -> bake) que Meshy no tiene
# (2-sep-2026: "no de la forma que describes"): Meshy pone el remesh, esto pone
# el horneado.
#
#   blender --background --factory-startup --python tools/hornear-normales.py -- \
#       <alto.glb> <bajo.glb> <salida.glb> [lado=2048] [extrusion=0.02] [rayo=0.1]
#
# `bajo` puede ser `decimar:N` para PROBAR la herramienta sin un remesh de Meshy:
# se decima el alto a N triangulos con las mismas UV (solo para medir; el asset
# de juego se remeshea en Meshy, que da quads y textura limpia).
#
# Los dos modelos tienen que estar en el MISMO espacio (los dos de Meshy del
# mismo generado, o los dos ya normalizados): el bake lanza rayos desde la
# superficie del bajo hacia el alto y lo que no encuentra en `rayo` unidades
# queda plano. `extrusion` es la jaula: cuanto se infla el bajo antes de
# lanzar, para cazar detalle que sobresale. Se miden en unidades del modelo
# (los master van a 1.9 de lado): 0.02 / 0.1 es un punto de partida, no un
# dial cerrado.
#
# Sale el bajo con su material y con el mapa horneado colgado del Normal Map
# (empaquetado en el GLB), listo para normalize-model.py como cualquier crudo.
import bpy, os, sys, time
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
if len(args) < 3:
    sys.exit("uso: hornear-normales.py <alto.glb> <bajo.glb|decimar:N> <salida.glb> [lado] [extrusion] [rayo]")
alto_p, bajo_p, salida = os.path.abspath(args[0]), args[1], os.path.abspath(args[2])
LADO = int(args[3]) if len(args) > 3 else 2048
EXTRUSION = float(args[4]) if len(args) > 4 else 0.02
RAYO = float(args[5]) if len(args) > 5 else 0.1

bpy.ops.wm.read_factory_settings(use_empty=True)


def importar(ruta, nombre):
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=ruta)
    nuevos = [o for o in bpy.data.objects if o not in antes and o.type == "MESH"]
    if not nuevos:
        sys.exit("RECHAZAR: %s no trae mallas" % ruta)
    for o in bpy.data.objects:
        o.select_set(False)
    for o in nuevos:
        o.select_set(True)
    bpy.context.view_layer.objects.active = nuevos[0]
    if len(nuevos) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = nombre
    # las transformaciones de objeto se aplican a la malla: el bake compara
    # superficies en mundo y Blender headless no evalua el depsgraph solo
    obj.data.transform(obj.matrix_world)
    obj.matrix_world.identity()
    return obj


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


alto = importar(alto_p, "alto")
if bajo_p.startswith("decimar:"):
    objetivo = int(bajo_p.split(":")[1])
    bajo = alto.copy(); bajo.data = alto.data.copy(); bajo.name = "bajo"
    bpy.context.scene.collection.objects.link(bajo)
    mod = bajo.modifiers.new("dec", "DECIMATE")
    mod.ratio = objetivo / max(tris(alto), 1)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(bajo.evaluated_get(dg))
    bajo.modifiers.clear()
    viejo = bajo.data; bajo.data = me; bpy.data.meshes.remove(viejo)
    for m in alto.data.materials:
        if m.name not in [x.name for x in bajo.data.materials]:
            bajo.data.materials.append(m)
    print("bajo decimado (solo prueba): %d tris" % tris(bajo))
else:
    bajo = importar(os.path.abspath(bajo_p), "bajo")
print("alto %d tris · bajo %d tris" % (tris(alto), tris(bajo)))
if not bajo.data.uv_layers:
    sys.exit("RECHAZAR: el bajo no trae UV — sin UV no hay donde hornear")

# el material del bajo es SUYO (copia): el alto conserva el original
if not bajo.data.materials:
    sys.exit("RECHAZAR: el bajo no trae material")
mat = bajo.data.materials[0].copy()
mat.name = "bajo_mat"
for i in range(len(bajo.data.materials)):
    bajo.data.materials[i] = mat
mat.use_nodes = True
nodos = mat.node_tree.nodes

# la imagen destino, activa en el arbol: es donde Blender hornea
img = bpy.data.images.new("normal_horneada", LADO, LADO, alpha=False)
img.colorspace_settings.name = "Non-Color"
nodo_img = nodos.new("ShaderNodeTexImage")
nodo_img.image = img
nodo_img.select = True
nodos.active = nodo_img

esc = bpy.context.scene
esc.render.engine = "CYCLES"
esc.cycles.device = "CPU"
esc.cycles.samples = 8
esc.render.bake.use_selected_to_active = True
esc.render.bake.cage_extrusion = EXTRUSION
esc.render.bake.max_ray_distance = RAYO
esc.render.bake.normal_space = "TANGENT"
esc.render.bake.margin = 16
esc.render.bake.use_clear = True

for o in bpy.data.objects:
    o.select_set(False)
alto.select_set(True)
bajo.select_set(True)
bpy.context.view_layer.objects.active = bajo
t0 = time.time()
bpy.ops.object.bake(type="NORMAL")
print("horneado en %.1f s" % (time.time() - t0))

# que el mapa tenga relieve de verdad (un bake fallido sale plano: 128,128,255)
px = np.array(img.pixels[:]).reshape(-1, 4)[:, :3]
desv = px.std(axis=0)
print("desviacion del mapa (r,g,b): %.3f %.3f %.3f" % tuple(desv))
if desv[0] < 0.005 and desv[1] < 0.005:
    sys.exit("RECHAZAR: el mapa horneado salio plano — los modelos no se solapan (espacio distinto) o el rayo es corto")

# colgar el mapa del Normal Map del BSDF, quitando el que traia
bsdf = next((n for n in nodos if n.type == "BSDF_PRINCIPLED"), None)
if bsdf is None:
    sys.exit("RECHAZAR: el material del bajo no tiene Principled BSDF")
nm = next((n for n in nodos if n.type == "NORMAL_MAP"), None)
if nm is None:
    nm = nodos.new("ShaderNodeNormalMap")
    mat.node_tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
for l in list(mat.node_tree.links):
    if l.to_node == nm and l.to_socket.name == "Color":
        viejo = l.from_node
        mat.node_tree.links.remove(l)
        if viejo.type == "TEX_IMAGE":
            nodos.remove(viejo)
mat.node_tree.links.new(nodo_img.outputs["Color"], nm.inputs["Color"])
nm.inputs["Strength"].default_value = 1.0
img.pack()

# fuera el alto: sale solo el bajo
bpy.data.objects.remove(alto, do_unlink=True)
os.makedirs(os.path.dirname(salida), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=True,
                          export_yup=True, use_selection=False, export_tangents=True,
                          export_image_format="AUTO")
print("escrito %s (%.1f MB) · %d tris · normal %dx%d" % (salida, os.path.getsize(salida) / 1048576.0, tris(bajo), LADO, LADO))
