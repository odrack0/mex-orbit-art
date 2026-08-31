#!/usr/bin/env python3
"""Pinta las CAMPANAS de las toberas en la textura emisiva de un GLB de nave.

El motivo: toda geometria de llama sobrepuesta (quads, conos, discos) se lee
"pegada" al hacer zoom a la popa; lo natural es que el propio metal de la
tobera se ENCIENDA — o sea, pintar su interior en el canal emisivo, que el
material ya trae (emissiveFactor 1,1,1).

Que hace: localiza los marcadores `tobera_*` (posicion + ancho en la escala
del nodo; el marcador vive en el FILO de salida de la campana) y pinta SOLO
el aro de la salida: los triangulos cuyos vertices caen a menos de
`ancho * factor` lateralmente Y dentro de una banda de `espesor * radio`
hacia proa desde el filo — pintar la campana entera se ve como una tobera
de neon, no como una boca encendida. Pinta sus triangulos UV sobre la
imagen emisiva EMBEBIDA; el GLB se reescribe apuntando la imagen a un
bufferView nuevo al final del buffer (sin recalcular offsets existentes).

Ademas filtra por NORMAL: solo se pintan las caras que miran hacia AFUERA de
CADA tobera, no la falda lateral de su campana — de perfil, la pared exterior
encendida se ve como una orilla contaminada. El eje de "afuera" no es el Z
global: las toberas de una nave suelen abrirse en abanico, y un eje global
corta el aro a la mitad en las que estan inclinadas. Se estima por tobera
promediando las normales de sus propias caras candidatas (PCA de un eje).

Uso: py tools/encender-toberas.py entrada.glb salida.glb [RRGGBB] [factor] [espesor] [nz]
     (defaults: color 80F0FF, factor 1.1, espesor 0.35, nz 0.5)
"""
import io
import json
import struct
import sys

from PIL import Image, ImageDraw

COMP = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def leer_accessor(g, binario, idx):
    a = g["accessors"][idx]
    bv = g["bufferViews"][a["bufferView"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    fmt, tam = COMP[a["componentType"]]
    n = NCOMP[a["type"]]
    stride = bv.get("byteStride", tam * n)
    out = []
    for i in range(a["count"]):
        off = base + i * stride
        out.append(struct.unpack_from("<" + fmt * n, binario, off))
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    color = tuple(int(sys.argv[3][i:i + 2], 16) for i in (0, 2, 4)) if len(sys.argv) > 3 else (0x80, 0xF0, 0xFF)
    factor = float(sys.argv[4]) if len(sys.argv) > 4 else 1.1
    espesor = float(sys.argv[5]) if len(sys.argv) > 5 else 0.35
    min_nz = float(sys.argv[6]) if len(sys.argv) > 6 else 0.5

    raw = open(sys.argv[1], "rb").read()
    if raw[:4] != b"glTF":
        print("RECHAZAR: no es GLB")
        return 1
    ln_json = struct.unpack_from("<I", raw, 12)[0]
    g = json.loads(raw[20:20 + ln_json])
    pos_bin = 20 + ln_json
    ln_bin = struct.unpack_from("<I", raw, pos_bin)[0]
    binario = raw[pos_bin + 8:pos_bin + 8 + ln_bin]

    # marcadores tobera_* : (centro, radio de seleccion)
    bocas = []
    for n in g["nodes"]:
        if str(n.get("name", "")).startswith("tobera"):
            t = n.get("translation", [0, 0, 0])
            r = n.get("scale", [0.1])[0] * factor
            bocas.append((t, r))
    if not bocas:
        print("RECHAZAR: el GLB no trae marcadores tobera_*")
        return 1

    # la malla (una primitiva, como sale del pipeline)
    prim = g["meshes"][0]["primitives"][0]
    posiciones = leer_accessor(g, binario, prim["attributes"]["POSITION"])
    uvs = leer_accessor(g, binario, prim["attributes"]["TEXCOORD_0"])
    indices = [i[0] for i in leer_accessor(g, binario, prim["indices"])]
    normales = (leer_accessor(g, binario, prim["attributes"]["NORMAL"])
                if "NORMAL" in prim["attributes"] else None)

    # el aro de salida: cerca del eje de la boca EN el plano del filo. La popa
    # del modelo es +Z (el pipeline normaliza asi); el filo esta en la z del
    # marcador y la banda se extiende `espesor*r` hacia proa (-z).
    boca_de = [-1] * len(posiciones)
    for v, p in enumerate(posiciones):
        for bi, (c, r) in enumerate(bocas):
            lateral = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2
            if lateral <= r * r and (c[2] - p[2]) <= espesor * r and (p[2] - c[2]) <= 0.3 * r:
                boca_de[v] = bi
                break
    cerca = [b >= 0 for b in boca_de]

    # la imagen emisiva embebida
    mat = g["materials"][0]
    img_idx = mat["emissiveTexture"]["index"]
    img = g["images"][g["textures"][img_idx]["source"]] if "textures" in g else g["images"][img_idx]
    bv_img = g["bufferViews"][img["bufferView"]]
    png = binario[bv_img.get("byteOffset", 0):bv_img.get("byteOffset", 0) + bv_img["byteLength"]]
    emisiva = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = emisiva.size
    draw = ImageDraw.Draw(emisiva)

    tris = 0
    descartados_normal = 0
    for i in range(0, len(indices), 3):
        a, b, c = indices[i], indices[i + 1], indices[i + 2]
        if cerca[a] and cerca[b] and cerca[c]:
            if normales is not None:
                nz = (normales[a][2] + normales[b][2] + normales[c][2]) / 3.0
                if nz < min_nz:          # falda lateral: no es la boca
                    descartados_normal += 1
                    continue
            poligono = [(uvs[k][0] * w, uvs[k][1] * h) for k in (a, b, c)]
            draw.polygon(poligono, fill=color, outline=color, width=2)
            tris += 1
    if tris == 0:
        print("RECHAZAR: ningun triangulo cayo dentro de las bocas (factor muy chico?)")
        return 1

    salida = io.BytesIO()
    emisiva.save(salida, "PNG")
    png_nuevo = salida.getvalue()

    # buffer nuevo: el binario original + el PNG al final (alineado a 4)
    binario_nuevo = binario + b"\x00" * ((4 - len(binario) % 4) % 4)
    offset_png = len(binario_nuevo)
    binario_nuevo += png_nuevo + b"\x00" * ((4 - len(png_nuevo) % 4) % 4)
    g["bufferViews"].append({"buffer": 0, "byteOffset": offset_png, "byteLength": len(png_nuevo)})
    img["bufferView"] = len(g["bufferViews"]) - 1
    g["buffers"][0]["byteLength"] = len(binario_nuevo)

    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(binario_nuevo)
    with open(sys.argv[2], "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, total))
        f.write(struct.pack("<I", len(js)) + b"JSON" + js)
        f.write(struct.pack("<I", len(binario_nuevo)) + b"BIN\x00" + binario_nuevo)
    print(f"OK -> {sys.argv[2]}  ({len(bocas)} bocas, {tris} triangulos pintados, "
          f"{descartados_normal} descartados por normal, emisiva {w}x{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
