"""Готическая каменная рама (RGBA, окна прозрачные) для каждой раскладки и каждого монитора."""
import math
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from layouts import LAYOUTS

S = 2
FD = "/usr/share/fonts/truetype/"
CIRCLES = [("I", "LIMBO", "Лимб"), ("II", "LUSSURIA", "Сладострастие"), ("III", "GOLA", "Чревоугодие"),
           ("IV", "AVARIZIA", "Скупость"), ("V", "IRA", "Гнев"), ("VI", "ERESIA", "Ересь"),
           ("VII", "VIOLENZA", "Насилие"), ("VIII", "MALEBOLGE", "Обман · Злые Щели"), ("IX", "TRADIMENTO", "Предательство")]
R_REL = 0.62
P_MAX = math.sqrt(R_REL ** 2 - (R_REL - 0.5) ** 2)


def arch_p(s):
    """Профиль стрельчатой арки: s — доля ширины от левого края (0..1); 0 у пяты, 1 в вершине."""
    s = min(s, 1 - s)
    return math.sqrt(max(R_REL ** 2 - (s - R_REL) ** 2, 0)) / P_MAX


def window_poly(win, inset=0.0):
    x0, y0, w, h, ha = win["x"] - inset, win["y"] - inset, win["w"] + 2 * inset, win["h"] + 2 * inset, win["ha"] + inset
    pts = [(x0, y0 + h)]
    for k in range(161):
        s = k / 160
        pts.append((x0 + s * w, y0 + ha * (1 - arch_p(s))))
    pts.append((x0 + w, y0 + h))
    return [(x * S, y * S) for x, y in pts]


def fbm(h, w, seed, octaves=7, base=6, pers=0.55):
    rng = np.random.default_rng(seed); out = np.zeros((h, w), np.float32); a = 1; t = 0
    for o in range(octaves):
        g = rng.random((int(base * 2 ** o) + 2, int(base * 2 ** o * w / h) + 2)).astype(np.float32)
        out += np.asarray(Image.fromarray(g, "F").resize((w, h), Image.BICUBIC)) * a; t += a; a *= pers
    return out / t


def mask_of(polys, W, H, blur=0.4):
    im = Image.new("L", (W, H), 0); d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon(p, fill=255)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur * S))
    return np.asarray(im, np.float32) / 255


def build(L, mon, seed=7):
    W, H = L["size"][0] * S, L["size"][1] * S
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    h = np.asarray(Image.fromarray(fbm(H // 2, W // 2, seed + mon, 7, 8), "F").resize((W, H), Image.BICUBIC))
    fine = np.asarray(Image.fromarray(fbm(H // 2, W // 2, 50, 5, 60), "F").resize((W, H), Image.BICUBIC))
    rowh = 44 * S; row = np.floor(yy / rowh); off = (row % 2) * 70 * S
    joint = (np.minimum(yy % rowh, rowh - yy % rowh) < 1.2 * S) | (np.minimum((xx + off) % (140 * S), 140 * S - (xx + off) % (140 * S)) < 1.2 * S)
    height = h * 0.8 + fine * 0.25 - joint * 0.35
    gy, gx = np.gradient(height * 30)
    n = np.dstack([-gx, -gy, np.ones_like(gx)]); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    Lv = np.array([-0.5, -0.7, 0.6]); Lv /= np.linalg.norm(Lv)
    diff = np.clip((n * Lv).sum(-1), 0, 1)
    col = np.array([0.105, 0.09, 0.085]) * (0.45 + 0.9 * h)[..., None] * (0.35 + 0.9 * diff)[..., None]
    wins = L["wins"]
    win = mask_of([window_poly(w) for w in wins], W, H)
    outer = mask_of([window_poly(w, 14) for w in wins], W, H)
    ring = np.clip(outer - win, 0, 1)
    bw = np.asarray(Image.fromarray((win * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10 * S)), np.float32) / 255
    by, bx = np.gradient(bw)
    shade = (bx * -0.5 + by * -0.7) / (np.hypot(bx, by) + 1e-6)
    col = col * (1 - ring[..., None] * 0.4) + ring[..., None] * np.array([0.16, 0.13, 0.11]) * (0.6 - 0.9 * shade)[..., None]
    g1 = np.clip(mask_of([window_poly(w, 22) for w in wins], W, H, 0.3) - mask_of([window_poly(w, 20) for w in wins], W, H, 0.3), 0, 1)
    goldc = np.array([0.85, 0.62, 0.28]) * (0.7 + 0.5 * fine)[..., None]
    col = col * (1 - g1[..., None]) + goldc * g1[..., None]
    sh = np.asarray(Image.fromarray((win * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(16 * S)), np.float32) / 255
    col *= (1 - 0.6 * np.clip(sh - win, 0, 1))[..., None]
    img = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8)); d = ImageDraw.Draw(img)
    # розетки между соседними окнами одного ряда
    for a, b in zip(wins, wins[1:]):
        if a["y"] != b["y"]:
            continue
        cx = (a["x"] + a["w"] + b["x"]) / 2 * S; cy = (a["y"] + a["ha"] * 0.3) * S
        r = 15 * S
        for k in range(4):
            an = k * math.pi / 2
            d.ellipse([cx + math.cos(an) * r - r, cy + math.sin(an) * r - r, cx + math.cos(an) * r + r, cy + math.sin(an) * r + r], outline=(150, 108, 54), width=2 * S)
        d.ellipse([cx - 6 * S, cy - 6 * S, cx + 6 * S, cy + 6 * S], fill=(120, 30, 20))
    # таблички с гравировкой
    for i, p in enumerate(L["plaques"]):
        ci = CIRCLES[mon * 3 + i]
        k = p["h"] / 140
        fnum = ImageFont.truetype(FD + "crosextra/Caladea-Bold.ttf", int(46 * S * k))
        fit = ImageFont.truetype(FD + "crosextra/Caladea-Regular.ttf", int(17 * S * max(k, 0.9)))
        fru = ImageFont.truetype(FD + "freefont/FreeSerifItalic.ttf", int(19 * S * max(k, 0.9)))
        cx, y0 = p["cx"] * S, p["y"] * S
        d.rounded_rectangle([cx - p["w"] / 2 * S, y0, cx + p["w"] / 2 * S, y0 + p["h"] * S], 6 * S, outline=(70, 56, 44), width=S)

        def engraved(xy, text, f):
            x, y = xy
            d.text((x + S, y + 1.5 * S), text, font=f, fill=(8, 6, 5), anchor="mm")
            d.text((x - 0.6 * S, y - 0.8 * S), text, font=f, fill=(250, 220, 160), anchor="mm")
            d.text((x, y), text, font=f, fill=(196, 146, 70), anchor="mm")
        engraved((cx, y0 + p["h"] * 0.29 * S), ci[0], fnum)
        engraved((cx, y0 + p["h"] * 0.59 * S), "  ".join(ci[1]), fit)
        engraved((cx, y0 + p["h"] * 0.79 * S), ci[2], fru)
    arr = np.asarray(img).astype(np.float32) / 255
    return Image.fromarray((np.clip(np.dstack([arr, 1 - win]), 0, 1) * 255).astype(np.uint8), "RGBA")


if __name__ == "__main__":
    for name, L in LAYOUTS.items():
        for m in range(3):
            build(L, m).save(f"out/frame_{name}_{m + 1}.webp", quality=92, method=6)
            print("frame", name, m + 1, flush=True)
