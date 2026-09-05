"""render_diagnostics - Blender diagnostic renders for low-poly auditing.

Renders each mesh from the real DarkOrbit gameplay camera (elevation 45 deg,
azimuth 25 deg, perspective FOV 30) plus a top view, in four passes:

    solid, wire, solidwire, density

`density` colours every triangle by how small it is relative to the asset:
hot = many small triangles = where the polygon budget was actually spent.

Run headless:
    blender -b -P render_diagnostics.py -- obj_dir out_dir [name1 name2 ...]
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

ELEV = 45.0
AZIM = 25.0
FOV = 30.0
RES = 900


def argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.film_transparent = False
    sc.display.shading.light = "STUDIO"
    sc.display.shading.studio_light = "Default"
    sc.display.shading.color_type = "SINGLE"
    sc.display.shading.single_color = (0.62, 0.64, 0.68)
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = "BOTH"
    sc.display.shading.curvature_ridge_factor = 1.0
    sc.display.shading.curvature_valley_factor = 1.0
    sc.display.render_aa = "8"
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("W")
    sc.world.color = (1, 1, 1)


def import_obj(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="NEGATIVE_Z", up_axis="Y")
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def bounds(objs):
    mn = Vector((1e18,) * 3)
    mx = Vector((-1e18,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    return mn, mx, (mn + mx) / 2, (mx - mn)


def place_camera(center, size, elev, azim, margin=1.16):
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens_unit = "FOV"
    cam_data.angle = math.radians(FOV)
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    radius = size.length * 0.5 * margin           # bounding-sphere radius
    dist = radius / math.tan(math.radians(FOV) / 2)
    e, a = math.radians(elev), math.radians(azim)
    # Blender is Z-up after the OBJ import conversion: azimuth turns around Z,
    # elevation lifts off the XY plane.
    cam.location = center + Vector((math.cos(e) * math.sin(a),
                                    -math.cos(e) * math.cos(a),
                                    math.sin(e))) * dist
    d = (center - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_start = dist * 0.01
    cam_data.clip_end = dist * 10
    bpy.context.scene.camera = cam
    return cam


def add_lights(center, size):
    for name, rot, energy in (("key", (-0.9, 0.35, 0.6), 3.0),
                              ("fill", (-0.5, -1.2, 0.2), 1.2)):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = rot
        bpy.context.scene.collection.objects.link(lo)


def make_wire(objs, thickness):
    wires = []
    mat = bpy.data.materials.new("wire")
    mat.use_nodes = False
    mat.diffuse_color = (0.03, 0.03, 0.05, 1)
    for o in objs:
        w = o.copy()
        w.data = o.data.copy()
        bpy.context.scene.collection.objects.link(w)
        m = w.modifiers.new("wf", "WIREFRAME")
        m.thickness = thickness
        m.use_replace = True
        m.use_boundary = True
        w.data.materials.clear()
        w.data.materials.append(mat)
        wires.append(w)
    return wires


def paint_density(objs, diag):
    """Per-face colour from triangle size: hot = small tris = spent budget."""
    import colorsys
    ref = diag * diag
    for o in objs:
        me = o.data
        if not me.color_attributes:
            me.color_attributes.new("dens", "BYTE_COLOR", "CORNER")
        col = me.color_attributes["dens"]
        bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
        areas = [f.calc_area() for f in bm.faces]
        bm.free()
        if not areas:
            continue
        # relative triangle "fineness": 0 = coarse, 1 = finest in this asset
        import statistics
        rel = [max(a, 1e-12) / ref for a in areas]
        lo = min(rel); hi = max(rel)
        import math as _m
        lg = [_m.log10(r) for r in rel]
        lmin, lmax = min(lg), max(lg)
        span = max(lmax - lmin, 1e-9)
        i = 0
        for p, f in enumerate(me.polygons):
            t = 1.0 - (lg[p] - lmin) / span            # 1 = smallest triangle
            r, g, b = colorsys.hsv_to_rgb(0.66 * (1.0 - t), 0.85, 1.0)
            for _ in f.loop_indices:
                col.data[i].color = (r, g, b, 1.0)
                i += 1
        mat = bpy.data.materials.new("dens")
        mat.use_nodes = True
        nt = mat.node_tree
        out = nt.nodes["Material Output"]
        for n in list(nt.nodes):
            if n != out:
                nt.nodes.remove(n)
        em = nt.nodes.new("ShaderNodeEmission")
        at = nt.nodes.new("ShaderNodeVertexColor")
        at.layer_name = "dens"
        nt.links.new(at.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        me.materials.clear()
        me.materials.append(mat)


def render_to(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def do_asset(obj_path, out_dir, name):
    results = {}
    for view, (elev, azim) in (("34", (ELEV, AZIM)), ("top", (89.5, 0.0))):
        # ---- solid + wire passes ----
        clean()
        objs = import_obj(obj_path)
        mn, mx, ctr, size = bounds(objs)
        diag = size.length
        place_camera(ctr, size, elev, azim)
        add_lights(ctr, size)
        render_to(os.path.join(out_dir, f"{name}_{view}_solid.png"))
        wires = make_wire(objs, diag * 0.0016)
        render_to(os.path.join(out_dir, f"{name}_{view}_solidwire.png"))
        for o in objs:
            o.hide_render = True
        bpy.context.scene.display.shading.single_color = (1, 1, 1)
        bpy.context.scene.world.color = (1, 1, 1)
        render_to(os.path.join(out_dir, f"{name}_{view}_wire.png"))
        results[view] = {"diag": diag, "size": list(size)}

        # ---- density pass ----
        clean()
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles.samples = 8
        objs = import_obj(obj_path)
        mn, mx, ctr, size = bounds(objs)
        place_camera(ctr, size, elev, azim)
        paint_density(objs, size.length)
        render_to(os.path.join(out_dir, f"{name}_{view}_density.png"))
    return results


def main():
    args = argv_after_dashes()
    obj_dir, out_dir = args[0], args[1]
    names = args[2:] or [os.path.splitext(f)[0] for f in sorted(os.listdir(obj_dir))
                         if f.endswith(".obj")]
    os.makedirs(out_dir, exist_ok=True)
    summary = {}
    for n in names:
        p = os.path.join(obj_dir, n + ".obj")
        if not os.path.exists(p):
            print("skip", n); continue
        print("### render", n, flush=True)
        summary[n] = do_asset(p, out_dir, n)
    with open(os.path.join(out_dir, "_render_index.json"), "w") as f:
        json.dump(summary, f, indent=1)


main()
