#!/usr/bin/env python3
"""ATF (Adobe Texture Format, Stage3D) -> PNG. Herramienta de REFERENCIA para
montar temporalmente assets del DarkOrbit original; el arte de MexOrbit no pasa
por aqui.

El ATF "comprimido" es un HIBRIDO (medido sobre los archivos reales, no el PDF):
por textura, los datos DXT van partidos en blobs con longitud uint32 BE:

  DXT1 (formato 2/3):  [LZMA selectores 4B/bloque] [JXR endpoints c0|c1]
  DXT5 (formato 4/5):  [LZMA indices alfa 6B/bloque] [JXR a0|a1]
                       [LZMA selectores color 4B/bloque] [JXR c0|c1]

El JXR de endpoints es una imagen de (w/4) x (h/2): la mitad superior es c0 por
bloque y la inferior c1 (565). Los LZMA son streams LZMA1 crudos con props(1) +
dictsize(4) delante. El JXR se decodifica con el WIC de Windows via PowerShell
(WmpBitmapDecoder) — esta herramienta es Windows-only, como el resto del banco.

Uso: py tools/atf2png.py entrada.atf salida.png
"""
import lzma
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image


def descomprimir_lzma(blob: bytes) -> bytes:
    props = blob[0]
    lc = props % 9
    rem = props // 9
    lp = rem % 5
    pb = rem // 5
    dic = struct.unpack_from("<I", blob, 1)[0]
    d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb, "dict_size": dic}])
    return d.decompress(blob[5:], max_length=64 * 1024 * 1024)


def decodificar_jxr(blob: bytes) -> np.ndarray:
    with tempfile.TemporaryDirectory() as td:
        jxr = os.path.join(td, "b.jxr")
        png = os.path.join(td, "b.png")
        open(jxr, "wb").write(blob)
        ps = (
            "Add-Type -AssemblyName PresentationCore;"
            f"$fs=[System.IO.File]::OpenRead('{jxr}');"
            "$d=New-Object System.Windows.Media.Imaging.WmpBitmapDecoder($fs,"
            "[System.Windows.Media.Imaging.BitmapCreateOptions]::None,"
            "[System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad);"
            "$e=New-Object System.Windows.Media.Imaging.PngBitmapEncoder;"
            "$e.Frames.Add([System.Windows.Media.Imaging.BitmapFrame]::Create($d.Frames[0]));"
            f"$o=[System.IO.File]::Create('{png}');$e.Save($o);$o.Close();$fs.Close()"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(png):
            raise RuntimeError(f"JXR no decodifico: {r.stderr[:300]}")
        return np.asarray(Image.open(png).convert("RGB"))


def leer_blobs(raw: bytes, pos: int, cuantos: int):
    out = []
    while pos + 4 <= len(raw) and len(out) < cuantos:
        n = struct.unpack_from(">I", raw, pos)[0]
        pos += 4
        out.append(raw[pos:pos + n])
        pos += n
    return out


def paleta_dxt1(c0: np.ndarray, c1: np.ndarray, v0: int, v1: int) -> list:
    pal = [c0, c1]
    if v0 > v1:
        pal.append((2 * c0.astype(int) + c1) // 3)
        pal.append((c0.astype(int) + 2 * c1) // 3)
    else:
        pal.append((c0.astype(int) + c1) // 2)
        pal.append(np.zeros(3, dtype=int))
    return pal


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    raw = open(sys.argv[1], "rb").read()
    if raw[:3] != b"ATF":
        print("RECHAZAR: no es ATF")
        return 1
    pos = 12 if raw[6] == 0xFF else 6
    fmt = raw[pos] & 0x7F
    w = 1 << raw[pos + 1]
    h = 1 << raw[pos + 2]
    pos += 4
    bw, bh = w // 4, h // 4
    nb = bw * bh
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., 3] = 255

    if fmt in (2, 3):
        sel_b, jxr_b = leer_blobs(raw, pos, 2)
        sel = descomprimir_lzma(sel_b)
        ep = decodificar_jxr(jxr_b)              # (h/2, w/4): c0 arriba, c1 abajo
    elif fmt in (4, 5):
        abits_b, ajxr_b, sel_b, jxr_b = leer_blobs(raw, pos, 4)
        abits = descomprimir_lzma(abits_b)
        aep = decodificar_jxr(ajxr_b)            # a0 arriba, a1 abajo (gris)
        sel = descomprimir_lzma(sel_b)
        ep = decodificar_jxr(jxr_b)
    else:
        print(f"RECHAZAR: formato ATF {fmt} sin decodificador")
        return 1

    if ep.shape[0] < 2 * bh or ep.shape[1] < bw or len(sel) < nb * 4:
        print(f"RECHAZAR: piezas no cuadran (endpoints {ep.shape}, sel {len(sel)}, bloques {nb})")
        return 1

    for by in range(bh):
        for bx in range(bw):
            i = by * bw + bx
            c0 = ep[by, bx].astype(int)
            c1 = ep[bh + by, bx].astype(int)
            v0 = ((c0[0] >> 3) << 11) | ((c0[1] >> 2) << 5) | (c0[2] >> 3)
            v1 = ((c1[0] >> 3) << 11) | ((c1[1] >> 2) << 5) | (c1[2] >> 3)
            pal = paleta_dxt1(c0, c1, v0, v1)
            bits = struct.unpack_from("<I", sel, i * 4)[0]
            if fmt in (4, 5):
                a0 = int(aep[by, bx][0])
                a1 = int(aep[bh + by, bx][0])
                apal = [a0, a1]
                if a0 > a1:
                    apal += [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
                else:
                    apal += [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
                ab = int.from_bytes(abits[i * 6:(i + 1) * 6], "little")
            for py in range(4):
                for px in range(4):
                    k = py * 4 + px
                    col = pal[(bits >> (2 * k)) & 3]
                    y, x = by * 4 + py, bx * 4 + px
                    out[y, x, 0], out[y, x, 1], out[y, x, 2] = col[0], col[1], col[2]
                    if fmt in (4, 5):
                        out[y, x, 3] = apal[(ab >> (3 * k)) & 7]
                    elif v0 <= v1 and ((bits >> (2 * k)) & 3) == 3:
                        out[y, x, 3] = 0
    Image.fromarray(out, "RGBA").save(sys.argv[2])
    print(f"OK -> {sys.argv[2]} ({w}x{h}, formato {fmt})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
