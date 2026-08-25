import sys, math
import numpy as np
from PIL import Image, ImageFilter

SRC   = sys.argv[1]
OUT   = sys.argv[2]
BANDS = int(sys.argv[3])   if len(sys.argv) > 3 else 16
UP    = int(sys.argv[4])   if len(sys.argv) > 4 else 3
EPS   = float(sys.argv[5]) if len(sys.argv) > 5 else 0.9
MINA  = float(sys.argv[6]) if len(sys.argv) > 6 else 6.0
# pasada cromatica: conserva decorados saturados (llamas, tribales) que la
# banda de luminancia convertiria en gris. 0 = desactivada.
CBANDS = int(sys.argv[7])   if len(sys.argv) > 7 else 6
CSAT   = float(sys.argv[8]) if len(sys.argv) > 8 else 0.28

img = Image.open(SRC).convert("RGBA")
W0, H0 = img.size
img = img.resize((W0 * UP, H0 * UP), Image.LANCZOS)
arr = np.array(img)
ship = arr[:, :, 3] > 120
rgb = np.array(Image.fromarray(arr[:, :, :3])
               .filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32)
lum = rgb[:, :, 0] * .299 + rgb[:, :, 1] * .587 + rgb[:, :, 2] * .114

vals = lum[ship]
qs = [np.quantile(vals, i / BANDS) for i in range(1, BANDS)]

# saturacion (HSV) para separar los decorados de color del metal
mx = rgb.max(axis=2)
mn = rgb.min(axis=2)
sat = np.where(mx > 1, (mx - mn) / np.maximum(mx, 1), 0.0)
chroma = ship & (sat > CSAT) & (mx > 45)

CW  = {(1, 0): (0, 1), (0, 1): (-1, 0), (-1, 0): (0, -1), (0, -1): (1, 0)}
CCW = {v: k for k, v in CW.items()}


def contours(mask):
    H, W = mask.shape
    P = np.zeros((H + 2, W + 2), dtype=bool)
    P[1:H + 1, 1:W + 1] = mask
    m = P[1:H + 1, 1:W + 1]
    top    = m & ~P[0:H,     1:W + 1]
    right  = m & ~P[1:H + 1, 2:W + 2]
    bottom = m & ~P[2:H + 2, 1:W + 1]
    left   = m & ~P[1:H + 1, 0:W]
    out = {}

    def add(sel, sx, sy, ex, ey):
        ys, xs = np.nonzero(sel)
        for y, x in zip(ys.tolist(), xs.tolist()):
            out.setdefault((x + sx, y + sy), []).append((x + ex, y + ey))

    add(top, 0, 0, 1, 0); add(right, 1, 0, 1, 1)
    add(bottom, 1, 1, 0, 1); add(left, 0, 1, 0, 0)

    loops = []
    for start in list(out.keys()):
        while out.get(start):
            loop, cur, d = [start], start, None
            while True:
                opts = out.get(cur)
                if not opts:
                    break
                if d is None or len(opts) == 1:
                    nx = opts.pop(0)
                else:
                    pick = None
                    for cand in (CW[d], d, CCW[d]):
                        t = (cur[0] + cand[0], cur[1] + cand[1])
                        if t in opts:
                            pick = t; break
                    if pick is None:
                        pick = opts[0]
                    opts.remove(pick); nx = pick
                if not out[cur]:
                    del out[cur]
                d = (nx[0] - cur[0], nx[1] - cur[1])
                if nx == start:
                    break
                loop.append(nx); cur = nx
            if len(loop) >= 4:
                loops.append(loop)
    return loops


def perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L == 0:
        return math.hypot(x - x1, y - y1)
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L


def dp(pts, eps):
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dmax, idx = 0.0, i
        for k in range(i + 1, j):
            dd = perp(pts[k], pts[i], pts[j])
            if dd > dmax:
                dmax, idx = dd, k
        if dmax > eps:
            keep[idx] = True
            stack.append((i, idx)); stack.append((idx, j))
    return [p for p, k in zip(pts, keep) if k]


def area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]; x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def build(mask):
    ds = []
    for lp in contours(mask):
        if area(lp) < MINA:
            continue
        k = max(range(len(lp)), key=lambda i: (lp[i][1], lp[i][0]))
        pts = lp[k:] + lp[:k] + [lp[k]]
        s = dp(pts, EPS)
        if len(s) > 2 and s[0] == s[-1]:
            s = s[:-1]
        if len(s) < 3 or area(s) < MINA:
            continue
        ds.append("M" + " ".join(f"{x/UP:.2f},{y/UP:.2f}" for x, y in s) + "Z")
    return "".join(ds)


def band_color(lo, hi, where=None):
    base = ship if where is None else where
    sel = base & (lum > lo) & (lum <= hi)
    if sel.sum() < 8:
        sel = base & (lum > lo - 6) & (lum <= hi + 6)
    if sel.sum() == 0:
        return "#808a99"
    c = rgb[sel].mean(axis=0)
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)


sil = build(ship)
# capa base: banda mas clara, cubre toda la silueta
top_c = band_color(qs[-1], 300)
parts = [f'<path fill="{top_c}" d="{sil}"/>']

# capas anidadas: cada mascara (lum <= t) es subconjunto de la anterior -> sin huecos
for i in range(len(qs) - 1, -1, -1):
    t = qs[i]
    lo = qs[i - 1] if i > 0 else -1
    d = build(ship & (lum <= t))
    if not d:
        continue
    parts.append(f'<path fill="{band_color(lo, t)}" d="{d}"/>')

# ---- pasada cromatica: decorados saturados sobre el metal ----
# Se agrupa primero por TONO y luego por luminancia dentro de cada tono. Si se
# bandea solo por luminancia, dos colores distintos con el mismo brillo (p.ej. un
# canon cian y un casco morado) caen en la misma banda y se promedian a un color
# intermedio, perdiendo ambos.
npx = int(chroma.sum())
if CBANDS > 0 and npx > 60:
    mx = rgb.max(axis=2); mn = rgb.min(axis=2)
    delta = np.maximum(mx - mn, 1e-6)
    r_, g_, b_ = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    hue = np.where(mx == r_, ((g_ - b_) / delta) % 6,
          np.where(mx == g_, (b_ - r_) / delta + 2, (r_ - g_) / delta + 4)) * 60.0

    NSECT = 6
    for k in range(NSECT):
        h0, h1 = k * 360.0 / NSECT, (k + 1) * 360.0 / NSECT
        sect = chroma & (hue >= h0) & (hue < h1)
        n = int(sect.sum())
        if n < 80:
            continue
        nb = max(2, min(CBANDS, int(round(CBANDS * min(1.0, n / max(npx, 1) * 3)))))
        cv = lum[sect]
        cqs = [np.quantile(cv, i / nb) for i in range(1, nb)]
        d = build(sect)
        if not d:
            continue
        parts.append(f'<path fill="{band_color(cqs[-1] if cqs else -1, 300, sect)}" d="{d}"/>')
        for i in range(len(cqs) - 1, -1, -1):
            t = cqs[i]
            lo = cqs[i - 1] if i > 0 else -1
            d = build(sect & (lum <= t))
            if d:
                parts.append(f'<path fill="{band_color(lo, t, sect)}" d="{d}"/>')

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W0} {H0}" width="{W0*4}" height="{H0*4}">',
       f"<title>MexOrbit — {__import__('os').path.splitext(__import__('os').path.basename(OUT))[0]} (vectorizado del render)</title>",
       f'<defs><clipPath id="s"><path d="{sil}"/></clipPath></defs>',
       '<g clip-path="url(#s)">'] + parts + ["</g></svg>"]
open(OUT, "w", encoding="utf-8").write("\n".join(svg))
print(f"capas={len(parts)}  pixeles_cromaticos={npx}")
