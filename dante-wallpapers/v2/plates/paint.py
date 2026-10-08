"""Мини-«живописец» на numpy: слои, туман, свечение, контровой свет."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 2                      # масштаб: виртуальные 560x930 -> 1120x1860
VW, VH = 560, 930
PW, PH = VW * S, VH * S

YY, XX = np.mgrid[0:PH, 0:PW].astype(np.float32)
XV, YV = XX / S, YY / S    # виртуальные координаты каждого пикселя


def C(*rgb):
    return np.array(rgb, np.float32) / 255.0


def fbm(h, w, seed, octaves=6, base=3, pers=0.55, warp=0.0):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        gh = int(base * 2 ** o) + 2
        gw = int(base * 2 ** o * w / h) + 2
        g = rng.random((gh, gw)).astype(np.float32)
        out += np.asarray(Image.fromarray(g, "F").resize((w, h), Image.BICUBIC)) * amp
        tot += amp; amp *= pers
    return out / tot


def noise(seed, octaves=6, base=3, pers=0.55, sx=1.0, sy=1.0):
    """Шум размером с плату; sx/sy растягивают (sx>1 — вытянутые по горизонтали пятна)."""
    h = max(8, int(PH / sy)); w = max(8, int(PW / sx))
    n = fbm(h, w, seed, octaves, base, pers)
    return np.asarray(Image.fromarray(n, "F").resize((PW, PH), Image.BICUBIC))


def line1d(seed, base, amp, n_ctrl=12, octaves=4):
    """Неровная линия y(x) в виртуальных координатах для каждого столбца пикселей."""
    rng = np.random.default_rng(seed)
    y = np.zeros(PW, np.float32); a = amp
    for o in range(octaves):
        k = n_ctrl * 2 ** o
        pts = rng.uniform(-1, 1, k + 1).astype(np.float32)
        y += np.interp(np.linspace(0, k, PW), np.arange(k + 1), pts) * a
        a *= 0.45
    k = np.exp(-np.linspace(-3, 3, 19) ** 2); k /= k.sum()
    sm = np.convolve(np.pad(y, 9, mode="edge"), k, mode="same")[9:-9]
    return base + sm


def below(line):
    """Маска «ниже линии» со сглаженным краем."""
    return np.clip((YV - line[None, :]) * S + 0.5, 0, 1)


def poly_mask(polys, blur=0.8):
    im = Image.new("L", (PW, PH), 0)
    d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon([(x * S, y * S) for x, y in p], fill=255)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur * S))
    return np.asarray(im, np.float32) / 255.0


def ellipse_mask(cx, cy, rx, ry, blur=0.8):
    im = Image.new("L", (PW, PH), 0)
    ImageDraw.Draw(im).ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur * S))
    return np.asarray(im, np.float32) / 255.0


def blurm(m, r):
    im = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(r * S))
    return np.asarray(im, np.float32) / 255.0


def sample(arr, xs, ys):
    """Билинейная выборка 2D-массива в дробных пиксельных координатах."""
    h, w = arr.shape
    xs = np.clip(xs, 0, w - 1.001); ys = np.clip(ys, 0, h - 1.001)
    x0 = xs.astype(np.int32); y0 = ys.astype(np.int32)
    fx = xs - x0; fy = ys - y0
    a = arr[y0, x0]; b = arr[y0, x0 + 1]; c = arr[y0 + 1, x0]; d = arr[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def vgrad(stops):
    ys = np.array([p for p, _ in stops], np.float32) * VH
    out = np.zeros((PH, PW, 3), np.float32)
    col = np.stack([np.interp(YV[:, 0], ys, [c[i] for _, c in stops]) for i in range(3)], -1)
    out[:] = col[:, None, :]
    return out


def lay(img, mask, col):
    """Наложить цвет (или массив) по маске."""
    m = mask[..., None]
    return img * (1 - m) + (col if np.ndim(col) == 3 else np.asarray(col)) * m


def glow(img, cx, cy, r, col, k=1.0, falloff=2.0, sy=1.0):
    d = np.sqrt((XV - cx) ** 2 + ((YV - cy) / sy) ** 2) / r
    g = 1.0 / (1.0 + d ** falloff) * np.exp(-d * 0.15)
    return img + g[..., None] * np.asarray(col) * k


def rim(mask, dx, dy, width=2.0):
    """Контровой свет: где маска есть, а сдвинутая в сторону света — нет."""
    sh = np.roll(np.roll(mask, int(-dy * width * S), 0), int(-dx * width * S), 1)
    return np.clip(mask - sh, 0, 1)


def fog(img, y0, y1, col, dens, seed, sx=6, drift=0):
    n = noise(seed, octaves=5, base=2, sx=sx, sy=1.2)
    band = np.clip((YV - y0) / max(1, (y1 - y0) * 0.35), 0, 1) * np.clip((y1 - YV) / max(1, (y1 - y0) * 0.35), 0, 1)
    a = np.clip(band * dens * (0.35 + 0.9 * n), 0, 1)[..., None]
    return img * (1 - a) + np.asarray(col) * a


def shafts(img, cx, cy, col, k, seed, n=24, spread=1.0):
    ang = np.arctan2(YV - cy, XV - cx)
    rng = np.random.default_rng(seed)
    s = np.zeros_like(ang)
    for _ in range(n):
        a0 = rng.uniform(-math.pi, math.pi) * spread; w = rng.uniform(0.01, 0.05)
        s += np.exp(-(((ang - a0 + math.pi) % (2 * math.pi) - math.pi) / w) ** 2) * rng.uniform(0.3, 1)
    d = np.hypot(XV - cx, YV - cy)
    s *= np.exp(-d / 500) * np.clip(d / 40, 0, 1)
    return img + s[..., None] * np.asarray(col) * k


def finish(img, seed, exposure=1.0, grain=0.018, vig=0.45, lift=(0.0, 0.0, 0.0)):
    img = np.clip(img, 0, None) * exposure
    img = 1 - np.exp(-img * 1.6)                       # мягкая тональная кривая
    img = img + np.asarray(lift) * (1 - img)
    nx = (XX / PW - 0.5) * 2; ny = (YY / PH - 0.5) * 2
    v = 1 - vig * np.clip(np.sqrt(nx ** 2 * 0.9 + ny ** 2 * 0.7) / 1.3, 0, 1) ** 2.2
    img = img * v[..., None]
    rng = np.random.default_rng(seed)
    img = img + rng.normal(0, grain, (PH, PW, 1)).astype(np.float32)
    return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))


# ---------- объём: перспектива, рельеф, свет, отражения ----------
_TEX = {}


def tex(seed, size=768, octaves=7, base=4, pers=0.55, ridged=False):
    key = (seed, size, octaves, base, pers, ridged)
    if key not in _TEX:
        t = fbm(size, size, seed, octaves, base, pers)
        if ridged:
            t = 1 - np.abs(t * 2 - 1)
        _TEX[key] = t
    return _TEX[key]


def mirror(u, n):
    m = np.mod(u, 2 * (n - 1))
    return np.where(m > n - 1, 2 * (n - 1) - m, m)


def tsample(T, u, v):
    h, w = T.shape
    return sample(T, mirror(u, w), mirror(v, h))


def ground_uv(horizon, cx=280, k=120.0, su=1.0, sv=1.0, f=420.0, sc=160.0):
    """Мировые координаты на горизонтальной плоскости (перспектива без растяжений)."""
    dy = np.maximum(YV - horizon, 0.35)
    return (XV - cx) / dy * sc * su, f / dy * sc * sv * 0.5, k / dy


def normals(h, strength):
    gy, gx = np.gradient(h * strength)
    n = np.stack([-gx, -gy, np.ones_like(h)], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def light(n, lights, ambient):
    """lights: ('point', x, y, z, color, range) | ('dir', dx, dy, dz, color)"""
    out = np.zeros(n.shape, np.float32) + np.asarray(ambient)
    for L in lights:
        if L[0] == "dir":
            l = np.array(L[1:4], np.float32); l /= np.linalg.norm(l)
            d = np.clip((n * l).sum(-1), 0, 1)
            out += d[..., None] * np.asarray(L[4])
        else:
            _, x, y, z, col, rng_ = L
            lx, ly, lz = x - XV, y - YV, np.full_like(XV, z)
            dist = np.sqrt(lx ** 2 + ly ** 2 + lz ** 2)
            d = np.clip((n[..., 0] * lx + n[..., 1] * ly + n[..., 2] * lz) / dist, 0, 1)
            att = 1.0 / (1.0 + (dist / rng_) ** 2)
            out += (d * att)[..., None] * np.asarray(col)
    return out


def material(img, mask, albedo, height, lights, ambient, strength=6.0):
    lit = light(normals(height, strength), lights, ambient)
    return lay(img, mask, np.asarray(albedo) * lit)


def reflect(img, horizon, mask, ripple=None, amp=3.0, tint=(1, 1, 1), k=0.7):
    """Отражение всего, что выше горизонта, в воде/льду ниже."""
    ys = 2 * horizon - YV
    xs = XV.copy()
    if ripple is not None:
        xs = xs + (ripple - 0.5) * amp * 2
        ys = ys + (ripple - 0.5) * amp
    out = np.stack([sample(img[..., c], xs * S, np.clip(ys, 0, VH - 1) * S) for c in range(3)], -1)
    return lay(img, mask * k, out * np.asarray(tint))
