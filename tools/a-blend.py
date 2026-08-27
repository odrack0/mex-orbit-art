# -*- coding: utf-8 -*-
"""Convierte un GLB en un .blend abrible de doble clic, con las texturas dentro.

El pipeline es headless a proposito, pero para MIRAR el modelo —comprobar una
bisagra, ver por que una pieza asoma— la interfaz es mejor herramienta. Esto
ahorra el baile de Archivo > Importar > glTF cada vez.

Deja la escena lista para inspeccionar:
  · las texturas EMPAQUETADAS, para que el .blend se pueda mover de sitio
  · la vista desde arriba, que es como se ve el bicho en el juego
  · una luz de sol a 315 grados, la misma del mundo (AssetDefs.LUZ_MUNDO_GRADOS)

  blender --background --factory-startup --python tools/a-blend.py -- \\
      <entrada.glb> <salida.blend>
"""
import bpy
import math
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salvaguarda import comprobar_salida    # noqa: E402
comprobar_salida(entrada, salida)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)

objs = [o for o in bpy.data.objects if o.type == "MESH"]
print("PIEZAS %d: %s" % (len(objs), ", ".join(o.name for o in objs)))
for o in objs:
    padre = o.parent.name if o.parent else "(raiz)"
    print("  %-18s local (%+.3f, %+.3f, %+.3f)  padre %s"
          % (o.name, o.location.x, o.location.y, o.location.z, padre))

# Empaquetadas: si no, el .blend apunta a archivos temporales que ya no existen.
try:
    bpy.ops.file.pack_all()
    print("TEXTURAS empaquetadas")
except RuntimeError as e:
    print("AVISO: no se pudieron empaquetar (%s)" % e)

sol_data = bpy.data.lights.new("sol_mundo", type="SUN")
sol_data.energy = 4.0
sol = bpy.data.objects.new("sol_mundo", sol_data)
bpy.context.scene.collection.objects.link(sol)
sol.rotation_euler = (math.radians(48), 0.0, math.radians(315))

# La vista guardada del .blend: mirando desde arriba, como el juego.
for area in getattr(bpy.context.screen, "areas", []):
    if area.type == "VIEW_3D":
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.shading.type = "MATERIAL"

bpy.ops.wm.save_as_mainfile(filepath=salida)
print("SALIDA %s  (%.1f MB)" % (salida, os.path.getsize(salida) / 1048576.0))
