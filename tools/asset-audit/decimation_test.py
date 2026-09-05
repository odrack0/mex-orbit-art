"""decimation_test - how far can a mesh be cut before it stops reading?

For each asset it builds copies at 100/75/50/25 % of the triangle count
(Blender's collapse decimator) and renders every level twice:

  * a "gameplay" render at the asset's REAL on-screen pixel size, using the
    DarkOrbit camera (elevation 45, azimuth 25, FOV 30) and the px/unit derived
    from the documented camera distance;
  * an inspection render at 900 px so the damage is actually visible.

It also writes the silhouette difference: renders each level as a black mask
and reports the share of pixels that changed against the original. That number,
not the triangle count, is what says whether a cut is safe.

    blender -b -P decimation_test.py -- obj_dir out_dir scales.json name1 name2
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ELEV, AZIM, FOV = 45.0, 25.0, 30.0
RATIOS = [1.0, 0.75, 0.5, 0.25]
INSPECT_RES = 720


def argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def setup(res, silhouette=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.film_transparent = True
    sc.display.shading.light = "FLAT" if silhouette else "STUDIO"
    sc.display.shading.color_type = "SINGLE"
    sc.display.shading.single_color = (0, 0, 0) if silhouette else (0.62, 0.64, 0.68)
    sc.display.shading.show_cavity = not silhouette
    sc.display.render_aa = "OFF" if silhouette else "8"
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("W")
    sc.world.color = (1, 1, 1)
    return sc


def import_obj(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="NEGATIVE_Z", up_axis="Y")
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def bounds(objs):
    mn = Vector((1e18,) * 3); mx = Vector((-1e18,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    return mn, mx, (mn + mx) / 2, (mx - mn)


def place_camera(center, size):
    cd = bpy.data.cameras.new("cam")
    cd.lens_unit = "FOV"; cd.angle = math.radians(FOV)
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    dist = size.length * 0.5 * 1.14 / math.tan(math.radians(FOV) / 2)
    e, a = math.radians(ELEV), math.radians(AZIM)
    cam.location = center + Vector((math.cos(e) * math.sin(a),
                                    -math.cos(e) * math.cos(a),
                                    math.sin(e))) * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    cd.clip_start = dist * 0.01; cd.clip_end = dist * 10
    bpy.context.scene.camera = cam


def lights():
    for rot, en in (((-0.9, 0.35, 0.6), 3.0), ((-0.5, -1.2, 0.2), 1.2)):
        ld = bpy.data.lights.new("l", "SUN"); ld.energy = en
        lo = bpy.data.objects.new("l", ld); lo.rotation_euler = rot
        bpy.context.scene.collection.objects.link(lo)


def decimate(objs, ratio):
    total = 0
    for o in objs:
        if ratio < 1.0:
            m = o.modifiers.new("dec", "DECIMATE")
            m.decimate_type = "COLLAPSE"
            m.ratio = ratio
        dg = bpy.context.evaluated_depsgraph_get()
        me = o.evaluated_get(dg).to_mesh()
        total += len(me.loop_triangles) if me.loop_triangles else sum(
            len(p.vertices) - 2 for p in me.polygons)
        o.evaluated_get(dg).to_mesh_clear()
    return total


def mask_pixels(path):
    img = bpy.data.images.load(path)
    px = list(img.pixels)
    n = len(px) // 4
    alpha = [px[i * 4 + 3] > 0.5 for i in range(n)]
    bpy.data.images.remove(img)
    return alpha


def run(obj_path, out_dir, name, px_per_unit):
    report = {"asset": name, "levels": []}
    masks = {}
    for ratio in RATIOS:
        tag = f"{int(ratio*100):03d}"
        # --- gameplay-size render ---
        setup(INSPECT_RES)
        objs = import_obj(obj_path)
        _mn, _mx, ctr, size = bounds(objs)
        tris = decimate(objs, ratio)
        place_camera(ctr, size); lights()
        gp_res = max(24, int(round(size.length * px_per_unit))) if px_per_unit else 96
        bpy.context.scene.render.resolution_x = gp_res
        bpy.context.scene.render.resolution_y = gp_res
        bpy.context.scene.render.filepath = os.path.join(
            out_dir, f"{name}_dec{tag}_game{gp_res}px.png")
        bpy.ops.render.render(write_still=True)
        bpy.context.scene.render.resolution_x = INSPECT_RES
        bpy.context.scene.render.resolution_y = INSPECT_RES
        bpy.context.scene.render.filepath = os.path.join(
            out_dir, f"{name}_dec{tag}_inspect.png")
        bpy.ops.render.render(write_still=True)

        # --- silhouette mask at gameplay size ---
        setup(gp_res, silhouette=True)
        objs = import_obj(obj_path)
        _mn, _mx, ctr, size = bounds(objs)
        decimate(objs, ratio)
        place_camera(ctr, size)
        mp = os.path.join(out_dir, f"_mask_{name}_{tag}.png")
        bpy.context.scene.render.filepath = mp
        bpy.ops.render.render(write_still=True)
        masks[tag] = mask_pixels(mp)
        report["levels"].append({"ratio": ratio, "tris": tris,
                                 "gameplay_px": gp_res})
    base = masks["100"]
    for lv in report["levels"]:
        tag = f"{int(lv['ratio']*100):03d}"
        m = masks[tag]
        diff = sum(1 for a, b in zip(base, m) if a != b)
        area = sum(1 for a in base if a)
        lv["silhouette_pixels"] = area
        lv["silhouette_changed_px"] = diff
        lv["silhouette_change_pct"] = round(100.0 * diff / max(area, 1), 2)
    return report


def main():
    args = argv_after_dashes()
    obj_dir, out_dir, scales_path = args[0], args[1], args[2]
    names = args[3:]
    os.makedirs(out_dir, exist_ok=True)
    scales = json.load(open(scales_path, encoding="utf-8"))
    reports = []
    for n in names:
        p = os.path.join(obj_dir, n + ".obj")
        if not os.path.exists(p):
            print("skip", n); continue
        ppu = scales.get(n, {}).get("px_per_unit_zoom1")
        print("### decimate", n, "px/u", ppu, flush=True)
        reports.append(run(p, out_dir, n, ppu))
    with open(os.path.join(out_dir, "_decimation.json"), "w") as f:
        json.dump(reports, f, indent=1)
    for r in reports:
        print(r["asset"])
        for lv in r["levels"]:
            print(f"   {int(lv['ratio']*100):3d}%  tris={lv['tris']:6d}  "
                  f"game={lv['gameplay_px']}px  silueta cambiada="
                  f"{lv['silhouette_change_pct']:.2f}%")


main()
