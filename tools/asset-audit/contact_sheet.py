#!/usr/bin/env python3
"""contact_sheet - compose the diagnostic renders into readable comparison
sheets (one PNG per asset, plus the decimation ladders).

    py contact_sheet.py renders out_dir asset1 asset2 ...
    py contact_sheet.py --decim decim out_dir asset1 ...
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

BG = (255, 255, 255)
FG = (20, 20, 24)
PAD = 10
LABEL_H = 26


def font(size=17):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def tile(paths, labels, cell, title, out_path, cols=None):
    imgs = []
    for p in paths:
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((cell, cell), Image.LANCZOS)
        else:
            im = Image.new("RGB", (cell, cell), (245, 245, 245))
        canvas = Image.new("RGB", (cell, cell), BG)
        canvas.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2))
        imgs.append(canvas)
    cols = cols or len(imgs)
    rows = (len(imgs) + cols - 1) // cols
    W = cols * cell + (cols + 1) * PAD
    H = rows * (cell + LABEL_H) + (rows + 1) * PAD + 34
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 8), title, fill=FG, font=font(20))
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        x = PAD + c * (cell + PAD)
        y = 34 + PAD + r * (cell + LABEL_H + PAD)
        sheet.paste(im, (x, y))
        d.rectangle([x, y, x + cell - 1, y + cell - 1], outline=(210, 210, 214))
        d.text((x + 2, y + cell + 4), labels[i], fill=(70, 70, 78), font=font(15))
    sheet.save(out_path)
    return out_path


def asset_sheet(render_dir, out_dir, name, cell=330):
    views = [("top", "solid"), ("top", "solidwire"), ("top", "density"),
             ("34", "solid"), ("34", "solidwire"), ("34", "wire")]
    paths = [os.path.join(render_dir, f"{name}_{v}_{k}.png") for v, k in views]
    labels = [f"cenital · {k}" for v, k in views[:3]] + \
             [f"3/4 (cam de juego) · {k}" for v, k in views[3:]]
    return tile(paths, labels, cell, name, os.path.join(out_dir, f"sheet_{name}.png"),
                cols=3)


def decim_sheet(decim_dir, out_dir, name, cell=300):
    rep = json.load(open(os.path.join(decim_dir, "_decimation.json")))
    r = next((x for x in rep if x["asset"] == name), None)
    paths, labels = [], []
    for lv in (r["levels"] if r else []):
        tag = f"{int(lv['ratio']*100):03d}"
        paths.append(os.path.join(decim_dir, f"{name}_dec{tag}_inspect.png"))
        labels.append(f"{int(lv['ratio']*100)}% · {lv['tris']} tris · silueta "
                      f"{lv['silhouette_change_pct']}%")
    for lv in (r["levels"] if r else []):
        tag = f"{int(lv['ratio']*100):03d}"
        paths.append(os.path.join(
            decim_dir, f"{name}_dec{tag}_game{lv['gameplay_px']}px.png"))
        labels.append(f"{int(lv['ratio']*100)}% a tamano real "
                      f"({lv['gameplay_px']}px)")
    return tile(paths, labels, cell,
                f"{name} — prueba de simplificacion (camara de juego 45/25, FOV 30)",
                os.path.join(out_dir, f"decim_{name}.png"), cols=4)


def main():
    if sys.argv[1] == "--decim":
        src, out = sys.argv[2], sys.argv[3]
        os.makedirs(out, exist_ok=True)
        for n in sys.argv[4:]:
            print(decim_sheet(src, out, n))
    else:
        src, out = sys.argv[1], sys.argv[2]
        os.makedirs(out, exist_ok=True)
        names = sys.argv[3:] or sorted({f.rsplit("_", 2)[0]
                                        for f in os.listdir(src)
                                        if f.endswith(".png")})
        for n in names:
            print(asset_sheet(src, out, n))


if __name__ == "__main__":
    main()
