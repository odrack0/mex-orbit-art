# -*- coding: utf-8 -*-
"""Pone en el modelo los marcadores de donde salen las llamas y los disparos.

Una NAVE necesita dos cosas que un bicho no: por donde escupen los motores y por
donde sale el laser. En 2D eso son puntos en pixeles de la textura, y funcionan
porque las llamas cuelgan del sprite y giran con el. En 3D el sprite YA NO GIRA
—gira el modelo dentro del viewport— asi que unas coordenadas de textura se
quedarian clavadas en pantalla mientras la nave da la vuelta.

La salida son nodos vacios dentro del GLB, `tobera_1..N` y `canon_izq`/`canon_der`,
con su posicion en unidades del MODELO. El cliente las lee y las gira con el rumbo,
que es lo unico que sobrevive a cualquier encuadre. Es la convencion que
`validar-modelo.py` ya comprueba desde antes de que existiera esta herramienta.

Las posiciones se MIDEN, no se escriben a mano:

  · TOBERAS. Se toma la banda de popa y se reparte en X. Las toberas salen como
    lobulos separados por valles —en el Phoenix, cuatro, con un valle de 12
    vertices en el centro— y de cada lobulo se coge su punto MAS TRASERO, que es
    por donde sale la llama, no su centro.
  · CANIONES. Se toman los vertices mas laterales, se parten por el signo de X y
    de cada lado se coge la punta DELANTERA del bloque. Un canion es un tubo: su
    boca es el extremo, no el centro de masa.

  blender --background --factory-startup --python marcar-anclajes.py -- \\
      <entrada.glb> <salida.glb> [frac_popa] [frac_lateral] [min_verts_lobulo]
"""
import bpy
import os
import sys

import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
# Fraccion del largo, contada desde la popa, donde viven las toberas.
FRAC_POPA = float(argv[2]) if len(argv) > 2 else 0.09
# Fraccion de la semianchura a partir de la cual un vertice cuenta como lateral.
FRAC_LATERAL = float(argv[3]) if len(argv) > 3 else 0.75
# Un lobulo con menos vertices que esto es ruido, no una tobera.
MIN_LOBULO = int(argv[4]) if len(argv) > 4 else 60
# Cuantas toberas tiene la nave. 0 = que las cuente por los valles. Se pasa a
# proposito: es un dato conocido del asset, y adivinarlo salio mal —los valles
# entre la tobera de fuera y la de dentro de cada lado son poco profundos (129
# vertices contra una media de 164) y el Phoenix salio con 2 en vez de 4.
N_TOBERAS = int(argv[5]) if len(argv) > 5 else 0

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salvaguarda import comprobar_salida    # noqa: E402
comprobar_salida(entrada, salida)

bpy.ops.wm.read_factory_settings(use_empty=True)
# Se borra lo que quede antes de importar: la escena por defecto de Blender deja
# una icosfera y coger "la primera malla" analiza esa.
for x in list(bpy.data.objects):
    bpy.data.objects.remove(x, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=entrada)

mallas = [o for o in bpy.data.objects if o.type == "MESH"]
if not mallas:
    print("ERROR: sin malla")
    sys.exit(1)
obj = max(mallas, key=lambda m: len(m.data.vertices))
raiz = obj
while raiz.parent is not None:
    raiz = raiz.parent

n = len(obj.data.vertices)
co = np.empty(n * 3, dtype=np.float32)
obj.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3).astype(np.float64)
lo, hi = co.min(axis=0), co.max(axis=0)
largo = hi[1] - lo[1]
semiancho = max(abs(lo[0]), abs(hi[0]))
print("MALLA %s  %d verts  caja (%.3f, %.3f, %.3f)" % (obj.name, n, *(hi - lo)))


def _partir(x, idx, n, bins):
    """Parte un grupo en `n` por sus valles, de dentro afuera."""
    if n <= 1 or len(idx) < 2 * MIN_LOBULO:
        return [idx]
    v = x[idx]
    cuenta, bordes = np.histogram(v, bins=bins)
    # Solo valen los cortes que dejan los DOS lados con tamanio suficiente. Sin
    # esa condicion el minimo se va siempre a los bins del borde, donde por
    # construccion hay pocos vertices, y el grupo no se llega a partir: el
    # Phoenix salia con 2 toberas en vez de 4.
    mejor, corte = None, None
    for k in range(1, len(cuenta) - 1):
        c = 0.5 * (bordes[k] + bordes[k + 1])
        na = int((v < c).sum())
        if na < MIN_LOBULO or len(idx) - na < MIN_LOBULO:
            continue
        if mejor is None or cuenta[k] < mejor:
            mejor, corte = cuenta[k], c
    if corte is None:
        return [idx]
    a, b = idx[v < corte], idx[v >= corte]
    na = max(1, min(n - 1, int(round(n * len(a) / float(len(idx))))))
    return _partir(x, a, na, bins) + _partir(x, b, n - na, bins)


def lobulos(x, cuantos=0, bins=48):
    """Parte un reparto en X en lobulos. Devuelve mascaras sobre `x`.

    Con `cuantos` a 0 corta por los valles claros. Con `cuantos` PAR se usa la
    SIMETRIA de la nave: se parte primero por el centro y cada lado en la mitad.
    Buscar los valles mas profundos sin mas no vale —los del Phoenix son de
    distinta hondura a izquierda y derecha, y el reparto salia asimetrico: una
    tobera de 181 vertices al lado de otra de 1125.
    """
    x = np.asarray(x)
    if cuantos <= 0:
        cuenta, bordes = np.histogram(x, bins=bins)
        umbral = max(1.0, cuenta.mean() * 0.20)
        grupos, actual = [], []
        for i, c in enumerate(cuenta):
            if c >= umbral:
                actual.append(i)
            elif actual:
                grupos.append((actual[0], actual[-1]))
                actual = []
        if actual:
            grupos.append((actual[0], actual[-1]))
        trozos = [np.nonzero((x >= bordes[a]) & (x <= bordes[b + 1]))[0] for a, b in grupos]
    else:
        idx = np.arange(len(x))
        if cuantos % 2 == 0:
            mitad = cuantos // 2
            trozos = (_partir(x, idx[x < 0.0], mitad, bins)
                      + _partir(x, idx[x >= 0.0], mitad, bins))
        else:
            trozos = _partir(x, idx, cuantos, bins)

    salida = []
    for t in trozos:
        if len(t) >= MIN_LOBULO:
            m = np.zeros(len(x), dtype=bool)
            m[t] = True
            salida.append(m)
    return salida


anclas = []

# ---- TOBERAS ----
corte = float(lo[1]) + FRAC_POPA * largo
popa = co[co[:, 1] < corte]
print("POPA   Y < %.3f  ->  %d verts" % (corte, len(popa)))
grupos = lobulos(popa[:, 0], N_TOBERAS)
print("TOBERAS %d lobulos" % len(grupos))
ordenados = sorted(grupos, key=lambda g: popa[g][:, 0].mean())
centros = [float(popa[m][:, 0].mean()) for m in ordenados]
# Separacion entre toberas, para medir el ancho de cada una en su propia ventana.
if len(centros) > 1:
    paso = (centros[-1] - centros[0]) / float(len(centros) - 1)
else:
    paso = semiancho
for i, m in enumerate(ordenados):
    c = popa[m]
    # El punto MAS TRASERO del lobulo, no su centro: la llama sale de la boca.
    trasero = c[c[:, 1] <= c[:, 1].min() + largo * 0.02]
    p = Vector((float(c[:, 0].mean()), float(trasero[:, 1].mean()), float(trasero[:, 2].mean())))
    # El ANCHO de la boca, medido en el punto mas trasero y por percentiles para
    # que un vertice suelto no lo infle. Va en la ESCALA del marcador, que es un
    # sitio estandar de glTF y llega al cliente sin inventar extensiones. Sirve
    # para que la llama mida lo que mide su tobera: con la separacion entre
    # toberas salian mas gruesas que las bocas de las que salen.
    # El ancho se mide en una VENTANA alrededor del centro, sobre la banda de popa
    # entera, y no sobre el lobulo que devolvio el corte: el corte del histograma
    # parte por el medio la tobera de fuera —salian 0,052 contra 0,151 de la de
    # dentro cuando en el render las cuatro son iguales— y ese ancho iba luego a
    # la llama.
    cerca = popa[(np.abs(popa[:, 0] - centros[i]) < paso * 0.5)
                 & (popa[:, 1] <= trasero[:, 1].max())]
    fuente = cerca if len(cerca) >= 30 else trasero
    ancho = float(np.percentile(fuente[:, 0], 92) - np.percentile(fuente[:, 0], 8))
    anclas.append(("tobera_%d" % (i + 1), p, len(c), max(ancho, 1e-4)))

# Las toberas de una nave son IGUALES por construccion —se ve en el render—, asi
# que se les da a todas la MEDIANA de lo medido. Es la mejor estimacion y ademas
# aguanta un corte malo: midiendo una por una salian 0,054 y 0,134 para dos bocas
# que en la imagen son la misma, porque el corte del histograma parte la de fuera.
if len(anclas) > 1:
    medios = sorted(a[3] for a in anclas)
    n_m = len(medios)
    mediana = medios[n_m // 2] if n_m % 2 else 0.5 * (medios[n_m // 2 - 1] + medios[n_m // 2])
    print("TOBERAS ancho por mediana: %.3f  (medidos %s)"
          % (mediana, ", ".join("%.3f" % m for m in medios)))
    anclas = [(a[0], a[1], a[2], mediana) for a in anclas]

# ---- CANIONES ----
lateral = co[np.abs(co[:, 0]) > FRAC_LATERAL * semiancho]
print("LATERAL |X| > %.3f  ->  %d verts" % (FRAC_LATERAL * semiancho, len(lateral)))
for nombre, signo in (("canon_izq", -1.0), ("canon_der", 1.0)):
    c = lateral[np.sign(lateral[:, 0]) == signo]
    if len(c) < MIN_LOBULO:
        print("  %s: solo %d verts, no se pone" % (nombre, len(c)))
        continue
    # La punta DELANTERA del bloque: un canion es un tubo y su boca es el extremo.
    frente = c[c[:, 1] >= c[:, 1].max() - largo * 0.04]
    p = Vector((float(frente[:, 0].mean()), float(frente[:, 1].mean()), float(frente[:, 2].mean())))
    ancho = float(np.percentile(frente[:, 0], 90) - np.percentile(frente[:, 0], 10))
    anclas.append((nombre, p, len(c), max(ancho, 1e-4)))

for nombre, p, cuantos, ancho in anclas:
    e = bpy.data.objects.new(nombre, None)
    e.empty_display_type = "PLAIN_AXES"
    e.empty_display_size = 0.05
    bpy.context.scene.collection.objects.link(e)
    e.location = p
    e.scale = (ancho, ancho, ancho)
    e.parent = raiz if raiz is not obj else None
    print("  %-10s (%+.3f, %+.3f, %+.3f)  ancho %.3f  de %d verts"
          % (nombre, p.x, p.y, p.z, ancho, cuantos))

if not anclas:
    print("AVISO: no se encontro ni una tobera ni un canion. Revisa las fracciones.")

bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True, export_skins=True, export_tangents=True,
                          export_extras=True)
print("PESO  %.1f MB -> %.1f MB" % (os.path.getsize(entrada) / 1048576.0,
                                    os.path.getsize(salida) / 1048576.0))
print("SALIDA %s" % salida)
