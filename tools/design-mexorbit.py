"""
Diseno propio MexOrbit "Obsidiana" sobre la geometria real de la Goliath.

No redibuja la nave: reutiliza el render original como fuente de forma y de luz, y
sustituye el material. El metal neutro se remapea a una rampa de obsidiana rematada
en oro, y las zonas de incrustacion reciben turquesa.

La mascara de incrustacion se toma de un diseno existente que ya coloca decorado en
sitios validos del casco (por defecto Bastion), asi la colocacion es coherente con
la nave y no inventada.

Uso:
  py -3 design-mexorbit.py <base.png> <mascara_diseno.png> <salida.svg>
                           [bandas] [escala] [epsilon] [area_min] [sat_mascara]
"""
import sys, math
import numpy as np
from PIL import Image, ImageFilter

SRC   = sys.argv[1]
MASKP = sys.argv[2]
OUT   = sys.argv[3]
BANDS = int(sys.argv[4])   if len(sys.argv) > 4 else 18
UP    = int(sys.argv[5])   if len(sys.argv) > 5 else 3
EPS   = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
MINA  = float(sys.argv[7]) if len(sys.argv) > 7 else 7.0
MSAT  = float(sys.argv[8]) if len(sys.argv) > 8 else 0.30
# radio de limpieza de la mascara: sube para quitar flecos finos del decorado
OPEN  = int(sys.argv[9])   if len(sys.argv) > 9 else 1

# ---------------- paletas ----------------
# obsidiana -> grafito -> oro especular
METAL = [
    (0.00, (0x0c, 0x0f, 0x14)),
    (0.25, (0x1b, 0x20, 0x29)),
    (0.45, (0x2c, 0x33, 0x3f)),
    (0.62, (0x41, 0x4a, 0x58)),
    (0.75, (0x5c, 0x66, 0x75)),
    (0.85, (0x7d, 0x88, 0x96)),
    (0.91, (0xa3, 0x94, 0x6a)),
    (0.96, (0xd8, 0xb9, 0x72)),
    (1.00, (0xf9, 0xed, 0xd4)),
]
# turquesa de incrustacion
INLAY = [
    (0.00, (0x04, 0x2a, 0x30)),
    (0.30, (0x0a, 0x5f, 0x6b)),
    (0.55, (0x14, 0x9b, 0xa6)),
    (0.78, (0x3d, 0xd2, 0xd6)),
    (1.00, (0xc6, 0xf7, 0xf7)),
]


def ramp(stops, t):
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if a <= t <= b:
            f = 0.0 if b == a else (t - a) / (b - a)
            return tuple(int(round(ca[k] + (cb[k] - ca[k]) * f)) for k in range(3))
    return stops[-1][1]


img = Image.open(SRC).convert("RGBA")
W0, H0 = img.size
img = img.resize((W0 * UP, H0 * UP), Image.LANCZOS)
arr = np.array(img)
ship = arr[:, :, 3] > 120
rgb = np.array(Image.fromarray(arr[:, :, :3])
               .filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32)
lum = rgb[:, :, 0] * .299 + rgb[:, :, 1] * .587 + rgb[:, :, 2] * .114

def bbox(m):
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


# mascara de incrustacion desde otro diseno.
# Los renders no comparten tamano exacto, asi que se alinea por la caja de la nave
# y no por el lienzo; si no, el decorado cae desplazado y salpica el casco.
msrc = Image.open(MASKP).convert("RGBA")
mraw = np.array(msrc)
mship = mraw[:, :, 3] > 120
mx0, my0, mx1, my1 = bbox(mship)
crop = msrc.crop((int(mx0), int(my0), int(mx1), int(my1)))

bx0, by0, bx1, by1 = bbox(ship)
crop = crop.resize((int(bx1 - bx0), int(by1 - by0)), Image.LANCZOS)
canvas = Image.new("RGBA", (W0 * UP, H0 * UP), (0, 0, 0, 0))
canvas.paste(crop, (int(bx0), int(by0)))

ma = np.array(canvas).astype(np.float32)
mmx = ma[:, :, :3].max(axis=2)
mmn = ma[:, :, :3].min(axis=2)
msat = np.where(mmx > 1, (mmx - mmn) / np.maximum(mmx, 1), 0.0)
inlay = ship & (ma[:, :, 3] > 120) & (msat > MSAT) & (mmx > 45)


def _shift(m, dy, dx):
    o = np.zeros_like(m)
    ys = slice(max(0, dy), m.shape[0] + min(0, dy))
    xs = slice(max(0, dx), m.shape[1] + min(0, dx))
    ys2 = slice(max(0, -dy), m.shape[0] + min(0, -dy))
    xs2 = slice(max(0, -dx), m.shape[1] + min(0, -dx))
    o[ys, xs] = m[ys2, xs2]
    return o


def opening(m, r=1):
    """Erosion + dilatacion: elimina motas sueltas sin comerse las zonas grandes."""
    e = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            e &= _shift(m, dy, dx)
    d = e.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d |= _shift(e, dy, dx)
    return d & m


inlay = opening(inlay, r=OPEN)

vals = lum[ship]
lo, hi = float(vals.min()), float(vals.max())
qs = [np.quantile(vals, i / BANDS) for i in range(1, BANDS)]

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


def hexc(c):
    return "#%02x%02x%02x" % c


def band_t(a, b, where):
    sel = where & (lum > a) & (lum <= b)
    if sel.sum() < 8:
        sel = where & (lum > a - 6) & (lum <= b + 6)
    if sel.sum() == 0:
        return 0.5
    return float((lum[sel].mean() - lo) / max(1e-6, hi - lo))


sil = build(ship)
parts = [f'<path fill="{hexc(ramp(METAL, band_t(qs[-1], 1e9, ship)))}" d="{sil}"/>']
for i in range(len(qs) - 1, -1, -1):
    t = qs[i]
    a = qs[i - 1] if i > 0 else -1
    d = build(ship & (lum <= t))
    if d:
        parts.append(f'<path fill="{hexc(ramp(METAL, band_t(a, t, ship)))}" d="{d}"/>')

# incrustacion de turquesa
if inlay.sum() > 60:
    iv = lum[inlay]
    ilo, ihi = float(iv.min()), float(iv.max())
    IB = 7
    iqs = [np.quantile(iv, k / IB) for k in range(1, IB)]

    def it(a, b):
        sel = inlay & (lum > a) & (lum <= b)
        if sel.sum() < 6:
            return 0.5
        return float((lum[sel].mean() - ilo) / max(1e-6, ihi - ilo))

    d = build(inlay)
    if d:
        parts.append(f'<path fill="{hexc(ramp(INLAY, it(iqs[-1], 1e9)))}" d="{d}"/>')
        for i in range(len(iqs) - 1, -1, -1):
            t = iqs[i]
            a = iqs[i - 1] if i > 0 else -1
            d = build(inlay & (lum <= t))
            if d:
                parts.append(f'<path fill="{hexc(ramp(INLAY, it(a, t)))}" d="{d}"/>')

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W0} {H0}" width="{W0*4}" height="{H0*4}">',
       "<title>MexOrbit Goliath — diseno Obsidiana</title>",
       f'<defs><clipPath id="s"><path d="{sil}"/></clipPath></defs>',
       '<g clip-path="url(#s)">'] + parts + ["</g></svg>"]
open(OUT, "w", encoding="utf-8").write("\n".join(svg))
print(f"capas={len(parts)}  pixeles_incrustacion={int(inlay.sum())}")
