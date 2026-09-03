# -*- coding: utf-8 -*-
"""Pone un esqueleto con pesos a un modelo entero, para que se doble sin romperse.

Sustituye a `partir-en-piezas.py` para todo lo que sea ANIMAR. Partir en piezas
funciona, pero es articulacion rigida: cada vertice pertenece ENTERO a una pieza,
asi que al rotar el ala su borde y el del cuerpo —que en reposo coincidian— se
separan y abren una rendija. Se ve, y no tiene arreglo dentro de ese enfoque.

Con esqueleto un vertice no pertenece a un hueso: PESA entre varios. Uno de la
bisagra puede ser 50% cuerpo y 50% ala, asi que al rotar se mueve a medias y la
superficie SE ESTIRA en vez de romperse. No hay costura porque no hubo corte.

Y sale mas barato de dibujar: una sola malla es una draw call por bicho en vez de
seis. Medido en el banco, por encima de 30 000 triangulos el cuello de botella
deja de ser la geometria y pasa a ser el numero de piezas.

Los pesos NO se pintan a mano: se derivan de la posicion con una transicion suave,
igual que se derivo la emision del color. La bisagra del ala y las bandas de cola
son las mismas que se midieron sobre la malla.

Entra un modelo ENTERO y SOLDADO (de `normalize-model.py`, que suelda desde el
arreglo de las esquirlas). Si entra partido en piezas, no sirve.

  blender --background --factory-startup --python riguear-modelo.py -- \\
      <entrada.glb> <salida.glb> [bisagra] [banda] [cola_desde] [cola_seg]
"""
import bpy
import math
import os
import sys

import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
entrada, salida = argv[0], argv[1]
BISAGRA = float(argv[2]) if len(argv) > 2 else 0.30
BANDA = float(argv[3]) if len(argv) > 3 else 0.22
COLA_DESDE = float(argv[4]) if len(argv) > 4 else 0.32
COLA_SEG = int(argv[5]) if len(argv) > 5 else 3
# Los cuernos, como fraccion del largo medida DESDE LA PROA. Medido sobre el
# Vexor: la zona son 944 verts (5,0% de la malla) en dos lobulos simetricos con
# un valle claro en el centro, que empiezan a Y=0.60 de una proa en 0.806.
CUERNO_DESDE = float(argv[6]) if len(argv) > 6 else 0.13
CUERNO_BANDA = float(argv[7]) if len(argv) > 7 else 0.075

# MODO RADIAL, por variable de entorno para no alargar mas la fila de
# posicionales. RADIAL=N monta N brazos alrededor del centro en vez de alas y
# cola: es la forma del Vorax nuevo, una estrella de tentaculos.
#
# Los angulos NO se reparten a 360/N. Se MIDEN de la malla, porque un modelo
# generado no sale simetrico: los ocho brazos del Vorax caen en 36, 84, 102, 122,
# 146, 188, 286 y 342 grados. Repartirlos a ojo habria puesto huesos entre dos
# brazos y ningun vertice pesaria del todo en ellos.
RADIAL = int(os.environ.get("RADIAL", "0"))
RADIAL_DESDE = float(os.environ.get("RADIAL_DESDE", "0.45"))   # radio, en fraccion del maximo
RADIAL_ARCO = float(os.environ.get("RADIAL_ARCO", "26"))       # medio ancho angular de un brazo
# Brazos que CUELGAN (tentaculos bajo un disco, ACI-02 2-sep-2026): el disco y los
# tentaculos comparten radio y angulo, y solo la ALTURA los separa. Con estos dos
# el peso lleva una tercera rampa por z: 0 en RADIAL_Z_DESDE (el borde del disco)
# y 1 en RADIAL_Z_HASTA (la punta), y los picos angulares se miden solo por
# debajo de RADIAL_Z_DESDE, que si no el borde del disco los tapa. Sin ellos,
# el rig radial plano de siempre (Vorax).
# GIRO_Z (env, grados): gira la MALLA sobre el eje vertical antes de riguear, para
# que la proa del rig (+Y) coincida con la cara del bicho que debe ir delante.
# El ACI-04 (2-sep-2026) traia el ojo y las manos en -Y: con 180 las manos caen
# en la zona de cuernos y el cliente no necesita `orientation.yaw`.
GIRO_Z = float(os.environ.get("GIRO_Z", "0"))
# CUERNO_X_MIN (env): los cuernos solo pesan desde este |X| hacia fuera. Para un
# par de MANOS que nacen a los lados de una cabeza redonda: sin esto, el polo
# delantero del cuerpo (|X| ~ 0) tambien pesa en los cuernos y la cara se pellizca.
CUERNO_X_MIN = float(os.environ.get("CUERNO_X_MIN", "0"))
RADIAL_Z_DESDE = os.environ.get("RADIAL_Z_DESDE")
RADIAL_Z_HASTA = os.environ.get("RADIAL_Z_HASTA")
COLGANTE = RADIAL_Z_DESDE is not None and RADIAL_Z_HASTA is not None
if COLGANTE:
    RADIAL_Z_DESDE = float(RADIAL_Z_DESDE)
    RADIAL_Z_HASTA = float(RADIAL_Z_HASTA)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salvaguarda import comprobar_salida    # noqa: E402
comprobar_salida(entrada, salida)


def suave(x):
    """smoothstep: arranca y termina sin canto. Con una rampa lineal la union se
    marca como un pliegue recto, que es justo lo que se viene a evitar."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=entrada)
mallas = [o for o in bpy.data.objects if o.type == "MESH"]
if len(mallas) != 1:
    print("ERROR: se esperaba UNA malla entera y llegaron %d (%s)."
          % (len(mallas), ", ".join(o.name for o in mallas)))
    print("       El esqueleto va sobre el modelo entero, no sobre uno ya partido.")
    sys.exit(1)
obj = mallas[0]

if GIRO_Z:
    from mathutils import Matrix
    obj.data.transform(Matrix.Rotation(math.radians(GIRO_Z), 4, "Z"))
    print("GIRO_Z %.0f: la malla gira sobre Z antes del rig" % GIRO_Z)
n = len(obj.data.vertices)
co = np.empty(n * 3, dtype=np.float32)
obj.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3).astype(np.float64)
lo, hi = co.min(axis=0), co.max(axis=0)
print("MALLA %s  %d verts  caja (%.3f, %.3f, %.3f)" % (obj.name, n, *(hi - lo)))

y_popa, y_proa = float(lo[1]), float(hi[1])
largo = y_proa - y_popa
y_cola = y_popa + COLA_DESDE * largo
bordes = ([y_cola - (y_cola - y_popa) * k / float(COLA_SEG) for k in range(COLA_SEG + 1)]
          if COLA_SEG > 0 else [y_popa])

# ---- el esqueleto ----
arm = bpy.data.armatures.new("esq")
esq = bpy.data.objects.new("esq", arm)
bpy.context.scene.collection.objects.link(esq)
bpy.context.view_layer.objects.active = esq
bpy.ops.object.mode_set(mode="EDIT")

# Todos los huesos apuntan a +Y (el eje del cuerpo) para que su marco local
# coincida con el del mundo en reposo. Asi el cliente puede rotar por ejes
# predecibles en vez de tener que adivinar el roll de cada hueso.
raiz = arm.edit_bones.new("raiz")
raiz.head, raiz.tail = Vector((0, 0, 0)), Vector((0, largo * 0.25, 0))

# ---- brazos radiales ----
angulos_brazo = []
if RADIAL > 0:
    rad_v = np.hypot(co[:, 0], co[:, 1])
    r_max = float(rad_v.max())
    r0 = RADIAL_DESDE * r_max
    fuera = rad_v > r0
    if COLGANTE:
        fuera = fuera & (co[:, 2] < RADIAL_Z_DESDE)
    ang_v = np.degrees(np.arctan2(co[fuera, 1], co[fuera, 0])) % 360.0
    # Histograma CIRCULAR: sin envolver, un brazo a 358 grados se parte en dos y
    # sale como dos brazos flacos en vez de uno.
    h, _ = np.histogram(ang_v, bins=180, range=(0, 360))
    k = np.array([1, 2, 3, 4, 5, 4, 3, 2, 1], float)
    k /= k.sum()
    hs = np.convolve(np.r_[h[-4:], h, h[:4]], k, mode="same")[4:-4]
    picos = [(i * 2.0, hs[i]) for i in range(180)
             if hs[i] >= hs[(i - 1) % 180] and hs[i] >= hs[(i + 1) % 180]]
    picos.sort(key=lambda t: -t[1])
    for a, _v in picos:
        if len(angulos_brazo) >= RADIAL:
            break
        # Se fusionan las crestas a menos de 15 grados: un brazo grueso da dos.
        if all(min(abs(a - b), 360 - abs(a - b)) > 15 for b in angulos_brazo):
            angulos_brazo.append(a)
    angulos_brazo.sort()
    if len(angulos_brazo) < RADIAL:
        print("AVISO: se pidieron %d brazos y la malla solo da %d picos claros"
              % (RADIAL, len(angulos_brazo)))
    for j, a in enumerate(angulos_brazo):
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        b = arm.edit_bones.new("brazo_%d" % (j + 1))
        if COLGANTE:
            # el hueso baja con el tentaculo: de la raiz bajo el disco a la punta
            b.head = Vector((ux * r0, uy * r0, RADIAL_Z_DESDE))
            b.tail = Vector((ux * r_max * 0.7, uy * r_max * 0.7, RADIAL_Z_HASTA))
        else:
            b.head = Vector((ux * r0, uy * r0, 0.0))
            b.tail = Vector((ux * r_max * 0.95, uy * r_max * 0.95, 0.0))
        b.parent = raiz
    print("RADIAL  %d brazos desde r=%.3f (max %.3f): %s"
          % (len(angulos_brazo), r0, r_max, ["%.0f" % a for a in angulos_brazo]))

# ALAS, si las hay. Un gusano no tiene, y forzar los diales para fingir que si
# es peor que no montarlas: con la bisagra por encima del ancho maximo los huesos
# se crean igual, sin un solo vertice que pese en ellos, y quedan en el GLB como
# partes moviles que no mueven nada. Un hueso muerto no avisa, se descubre el dia
# que alguien intenta animarlo.
#
# La senial es la malla, no un parametro aparte: si ningun vertice pasa la
# bisagra, ahi no hay ala que doblar.
hay_alas = bool((np.abs(co[:, 0]) > BISAGRA).any())
if hay_alas:
    y_ala = float(co[np.abs(co[:, 0]) > BISAGRA, 1].mean())
    for nombre, signo in (("ala_izq", -1.0), ("ala_der", 1.0)):
        b = arm.edit_bones.new(nombre)
        b.head = Vector((BISAGRA * signo, y_ala, 0.0))
        b.tail = Vector((BISAGRA * signo, y_ala + largo * 0.2, 0.0))
        b.parent = raiz
else:
    print("SIN ALAS  ningun vertice pasa la bisagra %.3f (ancho maximo %.3f)"
          % (BISAGRA, float(np.abs(co[:, 0]).max())))

# Los cuernos. La bisagra en X se MIDE de la malla (los dos lobulos del Vexor
# pican en +-0.075) en vez de fijarse: otro bicho tendra los suyos en otro sitio.
# CUERNOS, con CUERNO_DESDE <= 0 para saltarselos. Es el mismo criterio que las
# alas: no se monta un hueso que no va a mover nada. En el Vorax la pieza movil
# de la proa son los DIENTES, que no son un par simetrico partido por el signo de
# X sino un anillo alrededor de la boca — otra forma, otra decision, y se toma
# midiendo, no reutilizando la de al lado porque cae cerca.
y_cuerno = y_proa - CUERNO_DESDE * largo
banda_cuerno = max(1e-6, CUERNO_BANDA * largo)
hay_cuernos = CUERNO_DESDE > 0.0
if hay_cuernos:
    en_proa = (co[:, 1] > y_cuerno) & (np.abs(co[:, 0]) < BISAGRA)
    x_cuerno = float(np.abs(co[en_proa, 0]).mean()) if en_proa.any() else 0.06
    for nombre, signo in (("cuerno_izq", -1.0), ("cuerno_der", 1.0)):
        b = arm.edit_bones.new(nombre)
        b.head = Vector((x_cuerno * signo, y_cuerno, 0.0))
        b.tail = Vector((x_cuerno * signo, y_cuerno + largo * 0.08, 0.0))
        b.parent = raiz
else:
    print("SIN CUERNOS  CUERNO_DESDE=%.2f" % CUERNO_DESDE)

# COLA, con COLA_SEG <= 0 para saltarsela. Tercer interruptor con el mismo
# criterio que alas y cuernos, y hacia falta: intentar apagarla con los diales
# —un COLA_DESDE minusculo— no la apaga, deja `cola_1` cogiendo el peso entero
# encima del de `raiz`. La suma por vertice salio 2,000 exacto, que es la firma
# de dos huesos reclamando lo mismo al 100%.
hay_cola = COLA_SEG > 0
previo = raiz
for k in range(COLA_SEG if hay_cola else 0):
    b = arm.edit_bones.new("cola_%d" % (k + 1))
    b.head = Vector((0.0, bordes[k], 0.0))
    b.tail = Vector((0.0, bordes[k] - (bordes[k] - bordes[k + 1]) * 0.9, 0.0))
    b.parent = previo
    previo = b

bpy.ops.object.mode_set(mode="OBJECT")
print("HUESOS %s" % [b.name for b in arm.bones])

# ---- pesos por posicion ----
# El ala: 0 dentro del cuerpo, 1 fuera, con la transicion CENTRADA en la bisagra.
# Esa banda es la que se estira, y es la que hace que no haya costura.
ax = np.abs(co[:, 0])
# Sin alas el peso es CERO, no la rampa: si se dejara la rampa, los vertices del
# borde pesarian en un hueso que no existe y al normalizar le robarian peso al
# cuerpo, que es como se aplasta una malla sin que nadie sepa por que.
w_ala = suave((ax - (BISAGRA - BANDA * 0.5)) / BANDA) if hay_alas else np.zeros(n)
w_izq = np.where(co[:, 0] < 0, w_ala, 0.0)
w_der = np.where(co[:, 0] > 0, w_ala, 0.0)

# Los brazos: producto de dos rampas, radial y angular. Un vertice pertenece a un
# brazo si esta LEJOS del centro Y dentro de su arco; con solo una de las dos, el
# hueso se llevaria un anillo entero o una cuna que llega hasta el centro.
w_brazo = []
if angulos_brazo:
    rad_v = np.hypot(co[:, 0], co[:, 1])
    r_max = float(rad_v.max())
    r0 = RADIAL_DESDE * r_max
    w_r = suave((rad_v - r0) / max(1e-6, r_max - r0) * 2.0)
    if COLGANTE:
        # la tercera rampa: solo lo que cuelga por debajo del disco pesa
        w_r = w_r * suave((RADIAL_Z_DESDE - co[:, 2]) / max(1e-6, RADIAL_Z_DESDE - RADIAL_Z_HASTA))
    ang_v = np.degrees(np.arctan2(co[:, 1], co[:, 0])) % 360.0
    for a in angulos_brazo:
        d = np.abs(((ang_v - a + 180.0) % 360.0) - 180.0)
        w_brazo.append(w_r * suave((RADIAL_ARCO - d) / max(1e-6, RADIAL_ARCO * 0.6)))
    # Dos brazos vecinos pueden solaparse (los del Vorax caen a 18 grados uno de
    # otro). Se reparte entre ellos en vez de dejar que sumen mas de 1: un vertice
    # que pesa 1,4 se mueve mas de la cuenta, que es el mismo fallo que tuvieron
    # los cuernos.
    suma_b = np.sum(w_brazo, axis=0)
    exceso = np.maximum(suma_b, 1.0)
    w_brazo = [w / exceso for w in w_brazo]

# La cola: una rampa por frontera, y el peso de cada segmento es la diferencia
# entre su rampa y la del siguiente. Asi los pesos suman 1 por construccion.
if hay_cola:
    banda_cola = (y_cola - y_popa) / float(COLA_SEG) * 0.6
    rampas = [suave((bordes[k] - co[:, 1]) / max(1e-6, banda_cola)) for k in range(COLA_SEG + 1)]
    rampas.append(np.zeros(n))
    w_cola = [rampas[k] - rampas[k + 1] for k in range(COLA_SEG)]
else:
    rampas = [np.zeros(n)]
    w_cola = []

# Los cuernos: rampa hacia la proa, y solo en la parte CENTRAL — de la bisagra
# hacia fuera manda el ala, y un vertice que pesara en los dos se estiraria en
# dos direcciones a la vez.
w_cuerno = suave((co[:, 1] - y_cuerno) / banda_cuerno) if hay_cuernos else np.zeros(n)
# Se cede el terreno al ala de forma CONTINUA, no con un corte en la bisagra: con
# el corte, la franja |X| entre 0,19 y 0,30 pesaba en los dos y la suma llegaba a
# 1,416 —el vertice se movia mas de la cuenta.
w_cuerno = w_cuerno * (1.0 - w_ala)
if hay_cuernos and CUERNO_X_MIN > 0.0:
    # manos a los lados de una cabeza: el centro no pesa
    w_cuerno = w_cuerno * suave((np.abs(co[:, 0]) - CUERNO_X_MIN) / max(1e-6, CUERNO_X_MIN * 0.3))
w_c_izq = np.where(co[:, 0] < 0, w_cuerno, 0.0)
w_c_der = np.where(co[:, 0] > 0, w_cuerno, 0.0)

w_cuerpo = np.clip(1.0 - w_izq - w_der - rampas[0] - w_c_izq - w_c_der
                   - (np.sum(w_brazo, axis=0) if w_brazo else 0.0), 0.0, 1.0)

# La suma por vertice tiene que ser 1. Si algun vertice se queda sin peso, la
# piel lo colapsa al origen del hueso y la malla se aplasta — que es exactamente
# lo que hizo la primera version con la cola.
total = (w_cuerpo + w_izq + w_der + w_c_izq + w_c_der + sum(w_cola)
         + (np.sum(w_brazo, axis=0) if w_brazo else 0.0))
print("PESOS  suma por vertice: min %.3f  max %.3f  media %.3f"
      % (total.min(), total.max(), total.mean()))
huerfanos = int((total < 0.5).sum())
if huerfanos:
    print("  AVISO: %d vertices con menos de 0,5 de peso total (%.1f%%) — se aplastarian"
          % (huerfanos, 100.0 * huerfanos / n))

# Se normaliza SIEMPRE, no solo cuando falta peso. Al meter los cuernos aparecio
# el caso contrario —vertices sumando 1,416, que se mueven mas de la cuenta— y el
# guardian no lo veia porque solo miraba el minimo. Un peso que no suma 1 esta mal
# por los dos lados.
seguro = np.maximum(total, 1e-6)
w_cuerpo, w_izq, w_der = w_cuerpo / seguro, w_izq / seguro, w_der / seguro
w_c_izq, w_c_der = w_c_izq / seguro, w_c_der / seguro
w_cola = [w / seguro for w in w_cola]
w_brazo = [w / seguro for w in w_brazo]
print("  normalizado: suman 1 en todos")

grupos = {b.name: obj.vertex_groups.new(name=b.name) for b in arm.bones}
# Solo los huesos que EXISTEN: `vertex_groups.new` sobre un nombre sin hueso
# crea un grupo huerfano que el exportador arrastra al GLB.
pesos = {"raiz": w_cuerpo}
if hay_alas:
    pesos.update({"ala_izq": w_izq, "ala_der": w_der})
if hay_cuernos:
    pesos.update({"cuerno_izq": w_c_izq, "cuerno_der": w_c_der})
for k in range(len(w_cola)):
    pesos["cola_%d" % (k + 1)] = np.clip(w_cola[k], 0.0, 1.0)
for j in range(len(w_brazo)):
    pesos["brazo_%d" % (j + 1)] = np.clip(w_brazo[j], 0.0, 1.0)

for nombre, w in pesos.items():
    idx = np.nonzero(w > 0.001)[0]
    for i in idx:
        grupos[nombre].add([int(i)], float(w[i]), "REPLACE")
    mezcla = int(((w > 0.02) & (w < 0.98)).sum())
    print("  %-10s %6d verts con peso, %5d en la banda que se estira"
          % (nombre, len(idx), mezcla))

mod = obj.modifiers.new("arm", "ARMATURE")
mod.object = esq
obj.parent = esq

bpy.ops.export_scene.gltf(filepath=salida, export_format="GLB", export_apply=False,
                          export_yup=True, export_skins=True, export_tangents=True)
print("PESO  %.1f MB -> %.1f MB" % (os.path.getsize(entrada) / 1048576.0,
                                    os.path.getsize(salida) / 1048576.0))
print("SALIDA %s" % salida)
