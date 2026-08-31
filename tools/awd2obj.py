#!/usr/bin/env python3
"""AWD2 (Away3D) -> OBJ. Herramienta de REFERENCIA para montar temporalmente
las mallas del DarkOrbit original y compararlas; el arte final de MexOrbit sale
de su propio pipeline.

Lee la cabecera AWD ("AWD", version, flags, compresion, largo), descomprime el
cuerpo (zlib) y recorre los bloques extrayendo SOLO las geometrias de
triangulos (tipo 1): por cada sub-malla, sus streams de vertices (1), indices
(2) y UVs (3). Los streams declaran su tipo de dato, asi que la precision no se
adivina. Ejes: AWD/Away3D es ZURDO con Y arriba; se exporta espejando Z e
invirtiendo el orden de los triangulos para que Godot (diestro) lo lea derecho,
y con V invertida (OBJ usa V arriba).

Tambien exporta NORMALES: del stream tipo 4 si el AWD lo trae, o calculadas
por acumulacion de normales de cara (ponderadas por area) si no — sin `vn` el
importador de Godot deja la malla sin sombreado difuso y se ve como silueta.

Uso: py tools/awd2obj.py entrada.awd salida.obj
"""
import math
import struct
import sys
import zlib

TAM = {1: 1, 2: 2, 3: 4, 4: 1, 5: 2, 6: 4, 7: 4, 8: 8}
FMT = {1: "b", 2: "h", 3: "i", 4: "B", 5: "H", 6: "I", 7: "f", 8: "d"}


def leer_stream(cuerpo: bytes, pos: int):
    stype = cuerpo[pos]
    dtype = cuerpo[pos + 1]
    largo = struct.unpack_from("<I", cuerpo, pos + 2)[0]
    n = largo // TAM[dtype]
    datos = struct.unpack_from("<" + FMT[dtype] * n, cuerpo, pos + 6)
    return stype, list(datos), pos + 6 + largo


def leer_varstr(cuerpo: bytes, pos: int):
    n = struct.unpack_from("<H", cuerpo, pos)[0]
    return cuerpo[pos + 2:pos + 2 + n].decode("utf-8", "replace"), pos + 2 + n


def saltar_props(cuerpo: bytes, pos: int) -> int:
    largo = struct.unpack_from("<I", cuerpo, pos)[0]
    return pos + 4 + largo


def calcular_normales(verts: list, tris: list) -> list:
    """Normales por vertice: suma de normales de cara (el producto cruz sin
    normalizar pondera por area sola), normalizadas al final."""
    n = [0.0] * len(verts)
    for i in range(len(tris) // 3):
        a, b, c = tris[3 * i], tris[3 * i + 1], tris[3 * i + 2]
        ax, ay, az = verts[3 * a], verts[3 * a + 1], verts[3 * a + 2]
        ux, uy, uz = verts[3 * b] - ax, verts[3 * b + 1] - ay, verts[3 * b + 2] - az
        vx, vy, vz = verts[3 * c] - ax, verts[3 * c + 1] - ay, verts[3 * c + 2] - az
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        for k in (a, b, c):
            n[3 * k] += cx
            n[3 * k + 1] += cy
            n[3 * k + 2] += cz
    for i in range(len(n) // 3):
        m = math.sqrt(n[3 * i] ** 2 + n[3 * i + 1] ** 2 + n[3 * i + 2] ** 2)
        if m > 1e-12:
            n[3 * i] /= m
            n[3 * i + 1] /= m
            n[3 * i + 2] /= m
        else:
            n[3 * i + 1] = 1.0
    return n


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    raw = open(sys.argv[1], "rb").read()
    if raw[:3] != b"AWD":
        print("RECHAZAR: no es AWD")
        return 1
    compresion = raw[7]      # cabecera: AWD(3) + version(2) + flags u16(5-6) + compresion(7)
    cuerpo = raw[12:]
    if compresion == 1:
        cuerpo = zlib.decompress(cuerpo)
    elif compresion != 0:
        print(f"RECHAZAR: compresion {compresion} (lzma) sin soporte")
        return 1

    mallas = []          # [(nombre, verts, uvs, tris)]
    pos = 0
    while pos + 11 <= len(cuerpo):
        _bid, _ns, btype, _bflags = struct.unpack_from("<IBBB", cuerpo, pos)
        blargo = struct.unpack_from("<I", cuerpo, pos + 7)[0]
        binicio = pos + 11
        pos = binicio + blargo
        if btype != 1:                      # solo TriangleGeometry
            continue
        p = binicio
        nombre, p = leer_varstr(cuerpo, p)
        subs = struct.unpack_from("<H", cuerpo, p)[0]   # num_subs es uint16
        p += 2
        p = saltar_props(cuerpo, p)
        for _ in range(subs):
            sub_largo = struct.unpack_from("<I", cuerpo, p)[0]
            p += 4
            fin_sub = p + sub_largo
            p = saltar_props(cuerpo, p)
            verts, uvs, tris, norms = [], [], [], []
            while p < fin_sub:
                stype, datos, p = leer_stream(cuerpo, p)
                if stype == 1:
                    verts = datos
                elif stype == 2:
                    tris = datos
                elif stype == 3:
                    uvs = datos
                elif stype == 4:
                    norms = datos
            p = saltar_props(cuerpo, p)     # atributos de usuario del sub
            if verts and tris:
                if not norms:
                    norms = calcular_normales(verts, tris)
                mallas.append((nombre or f"sub{len(mallas)}", verts, uvs, tris, norms))
        # atributos de usuario del bloque: ya quedaron dentro de blargo

    if not mallas:
        print("RECHAZAR: el AWD no trae geometrias de triangulos")
        return 1

    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(f"# awd2obj de {sys.argv[1]}\n")
        base_v = 1
        base_t = 1
        for nombre, verts, uvs, tris, norms in mallas:
            f.write(f"o {nombre}\n")
            nv = len(verts) // 3
            for i in range(nv):
                x, y, z = verts[3 * i], verts[3 * i + 1], verts[3 * i + 2]
                f.write(f"v {x:.6f} {y:.6f} {-z:.6f}\n")   # espejo Z: zurdo->diestro
            for i in range(nv):
                nx, ny, nz = norms[3 * i], norms[3 * i + 1], norms[3 * i + 2]
                f.write(f"vn {nx:.4f} {ny:.4f} {-nz:.4f}\n")   # mismo espejo que v
            nuv = len(uvs) // 2
            for i in range(nuv):
                f.write(f"vt {uvs[2 * i]:.6f} {1.0 - uvs[2 * i + 1]:.6f}\n")
            for i in range(len(tris) // 3):
                a, b, c = tris[3 * i] + base_v, tris[3 * i + 1] + base_v, tris[3 * i + 2] + base_v
                if nuv:
                    at, bt, ct = tris[3 * i] + base_t, tris[3 * i + 1] + base_t, tris[3 * i + 2] + base_t
                    f.write(f"f {a}/{at}/{a} {c}/{ct}/{c} {b}/{bt}/{b}\n")   # orden invertido con el espejo
                else:
                    f.write(f"f {a}//{a} {c}//{c} {b}//{b}\n")
            base_v += nv
            base_t += max(nuv, 1)
    total_v = sum(len(v) // 3 for _, v, _, _, _ in mallas)
    total_t = sum(len(t) // 3 for _, _, _, t, _ in mallas)
    print(f"OK -> {sys.argv[2]}  ({len(mallas)} sub-mallas, {total_v} verts, {total_t} tris)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
