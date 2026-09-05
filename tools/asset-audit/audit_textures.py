#!/usr/bin/env python3
"""audit_textures - inventory of an ATF (Stage3D) texture folder.

Reads only the ATF header (format, width, height, mip count) so it is fast and
needs no DXT/JXR decoding. Groups files by asset and channel so we can answer
"what texture budget did this asset actually ship with?".

    py audit_textures.py <folder> out.csv
"""
from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict

ATF_FORMATS = {
    0: "RGBA888", 1: "RGBA_JPEGXR", 2: "COMPRESSED(DXT1/PVRTC/ETC1)",
    3: "RAW_COMPRESSED", 4: "COMPRESSED_ALPHA(DXT5)", 5: "RAW_COMPRESSED_ALPHA",
    12: "COMPRESSED_LOSSY", 13: "COMPRESSED_LOSSY_ALPHA",
}
CHANNELS = ("diffuse", "glow", "specular", "normal", "alpha", "ao", "bump",
            "ambient", "mask", "spec", "clean")


def read_header(path):
    with open(path, "rb") as fh:
        raw = fh.read(24)
    if raw[:3] != b"ATF":
        return None
    pos = 12 if raw[6] == 0xFF else 6
    fmt = raw[pos] & 0x7F
    cube = bool(raw[pos] & 0x80)
    w = 1 << raw[pos + 1]
    h = 1 << raw[pos + 2]
    mips = raw[pos + 3]
    return {"format_id": fmt, "format": ATF_FORMATS.get(fmt, f"?{fmt}"),
            "width": w, "height": h, "mips": mips, "cube": cube}


def split_name(stem):
    """'goliath-elite_glow_512' -> ('goliath-elite', 'glow', 512)."""
    m = re.match(r"^(.*)_([0-9]+)$", stem)
    size = int(m.group(2)) if m else None
    rest = m.group(1) if m else stem
    chan = ""
    for c in CHANNELS:
        if rest.endswith("_" + c):
            chan = c
            rest = rest[: -len(c) - 1]
            break
    return rest, chan, size


def main():
    folder, out_csv = sys.argv[1], sys.argv[2]
    rows = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(".atf"):
            continue
        p = os.path.join(folder, f)
        hdr = read_header(p)
        stem = os.path.splitext(f)[0]
        asset, chan, size = split_name(stem)
        row = {"file": f, "asset": asset, "channel": chan or "?",
               "name_size": size, "bytes": os.path.getsize(p)}
        row.update(hdr or {})
        rows.append(row)
    keys = ["file", "asset", "channel", "name_size", "width", "height",
            "mips", "format", "format_id", "cube", "bytes"]
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    per_asset = defaultdict(set)
    for r in rows:
        per_asset[r["asset"]].add(r["channel"])
    from collections import Counter
    print(f"{len(rows)} ATF, {len(per_asset)} assets con textura")
    print("canales:", Counter(r["channel"] for r in rows).most_common())
    print("formatos:", Counter(r.get("format") for r in rows).most_common())
    print("tamanos reales:", Counter(f'{r.get("width")}x{r.get("height")}'
                                     for r in rows).most_common(10))
    print("mips:", Counter(r.get("mips") for r in rows).most_common())
    combos = Counter("+".join(sorted(v)) for v in per_asset.values())
    print("\ncombinaciones de canal por asset:")
    for k, v in combos.most_common(12):
        print(f"   {v:4d}  {k}")


if __name__ == "__main__":
    main()
