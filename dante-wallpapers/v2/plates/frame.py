"""Готическая каменная рама-триптих 3840x2160 (RGBA, окна прозрачные) для каждого монитора."""
import math
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2
W, H = 1920 * S, 1080 * S
WIN_W, WIN_H, TOP, GAP = 560, 930, 30, 60
FD = "/usr/share/fonts/truetype/"
CIRCLES = [("I", "LIMBO", "Лимб"), ("II", "LUSSURIA", "Сладострастие"), ("III", "GOLA", "Чревоугодие"),
           ("IV", "AVARIZIA", "Скупость"), ("V", "IRA", "Гнев"), ("VI", "ERESIA", "Ересь"),
           ("VII", "VIOLENZA", "Насилие"), ("VIII", "MALEBOLGE", "Обман · Злые Щели"), ("IX", "TRADIMENTO", "Предательство")]


def fbm(h, w, seed, octaves=7, base=6, pers=0.55):
    rng = np.random.default_rng(seed); out = np.zeros((h, w), np.float32); a = 1; t = 0
    for o in range(octaves):
        g = rng.random((int(base * 2 ** o) + 2, int(base * 2 ** o * w / h) + 2)).astype(np.float32)
        out += np.asarray(Image.fromarray(g, "F").resize((w, h), Image.BICUBIC)) * a; t += a; a *= pers
    return out / t


def window_poly(i, inset=0.0):
    x0 = GAP + i * (WIN_W + GAP) + inset; x1 = x0 + WIN_W - 2 * inset
    w = x1 - x0; r = 0.62 * WIN_W - inset * 0.4
    h = math.sqrt(max(r ** 2 - (r - w / 2) ** 2, 1))
    ys = TOP + inset + h
    pts = [(x0, TOP + WIN_H - inset)]
    cxl = x0 + r
    for t in np.linspace(0, 1, 60):  # левая дуга: от точки пяты до вершины
        a = math.pi + t * (math.acos((w / 2 - r) / -r) - math.pi) if False else None
    # строим дугу численно
    for t in np.linspace(0, 1, 80):
        x = x0 + t * w / 2
        y = ys - math.sqrt(max(r ** 2 - (x - cxl) ** 2, 0))
        pts.append((x, y))
    cxr = x1 - r
    for t in np.linspace(0, 1, 80):
        x = x0 + w / 2 + t * w / 2
        y = ys - math.sqrt(max(r ** 2 - (x - cxr) ** 2, 0))
        pts.append((x, y))
    pts.append((x1, TOP + WIN_H - inset))
    return [(x * S, y * S) for x, y in pts], ys


def mask_of(polys, blur=0.6):
    im = Image.new("L", (W, H), 0); d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon(p, fill=255)
    return np.asarray(im.filter(ImageFilter.GaussianBlur(blur * S)) if blur else im, np.float32) / 255


def build(mon):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # камень: рельеф + швы кладки
    h = fbm(H // 2, W // 2, 7 + mon, 7, 8)
    h = np.asarray(Image.fromarray(h, "F").resize((W, H), Image.BICUBIC))
    fine = np.asarray(Image.fromarray(fbm(H // 2, W // 2, 50, 5, 60), "F").resize((W, H), Image.BICUBIC))
    rowh = 44 * S
    row = np.floor(yy / rowh)
    off = (row % 2) * 70 * S
    joint = (np.minimum(yy % rowh, rowh - yy % rowh) < 1.2 * S) | (np.minimum((xx + off) % (140 * S), 140 * S - (xx + off) % (140 * S)) < 1.2 * S)
    height = h * 0.8 + fine * 0.25 - joint * 0.35
    gy, gx = np.gradient(height * 30)
    n = np.dstack([-gx, -gy, np.ones_like(gx)]); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    L = np.array([-0.5, -0.7, 0.6]); L /= np.linalg.norm(L)
    diff = np.clip((n * L).sum(-1), 0, 1)
    stone = np.array([0.105, 0.09, 0.085]) * (0.45 + 0.9 * h)[..., None]
    col = stone * (0.35 + 0.9 * diff)[..., None]

    windows, bevels, gold = [], [], []
    for i in range(3):
        p, ys = window_poly(i)
        windows.append(p)
    win = mask_of(windows, 0.4)
    # фаска вокруг окна: светлая сверху-слева, тень снизу-справа
    outer = mask_of([window_poly(i, -14)[0] for i in range(3)], 0.5)
    ring = np.clip(outer - win, 0, 1)
    ox = (xx[:, :] * 0); 
    # направление фаски — через градиент расстояния (размытая маска окна)
    bw = np.asarray(Image.fromarray((win * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10 * S)), np.float32) / 255
    by, bx = np.gradient(bw)
    shade = (bx * -0.5 + by * -0.7) / (np.hypot(bx, by) + 1e-6)
    col = col * (1 - ring[..., None] * 0.4) + ring[..., None] * np.array([0.16, 0.13, 0.11]) * (0.6 - 0.9 * shade)[..., None]
    # золотая инкрустация вокруг окон
    g1 = mask_of([window_poly(i, -22)[0] for i in range(3)], 0.3) - mask_of([window_poly(i, -20)[0] for i in range(3)], 0.3)
    g1 = np.clip(g1, 0, 1)
    goldc = np.array([0.85, 0.62, 0.28]) * (0.7 + 0.5 * fine)[..., None]
    col = col * (1 - g1[..., None]) + goldc * g1[..., None]
    # тень окна на камне (окно утоплено)
    sh = np.asarray(Image.fromarray((win * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(16 * S)), np.float32) / 255
    col *= (1 - 0.6 * np.clip(sh - win, 0, 1))[..., None]

    img = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    # розетки-четырёхлистники между арками
    for i in range(4):
        cx = (GAP / 2 + i * (WIN_W + GAP)) * S; cy = 150 * S
        if i in (0, 3):
            continue
        for k in range(4):
            a = k * math.pi / 2
            r = 15 * S
            d.ellipse([cx + math.cos(a) * r - r, cy + math.sin(a) * r - r, cx + math.cos(a) * r + r, cy + math.sin(a) * r + r], outline=(150, 108, 54), width=2 * S)
        d.ellipse([cx - 6 * S, cy - 6 * S, cx + 6 * S, cy + 6 * S], fill=(120, 30, 20))
    # подписи-гравировка под окнами
    fnum = ImageFont.truetype(FD + "crosextra/Caladea-Bold.ttf", 46 * S)
    fit = ImageFont.truetype(FD + "crosextra/Caladea-Regular.ttf", 17 * S)
    fru = ImageFont.truetype(FD + "freefont/FreeSerifItalic.ttf", 19 * S)
    for i in range(3):
        ci = CIRCLES[mon * 3 + i]
        cx = (GAP + i * (WIN_W + GAP) + WIN_W / 2) * S
        y0 = (TOP + WIN_H + 10) * S
        # утопленная табличка
        d.rounded_rectangle([cx - 200 * S, y0, cx + 200 * S, y0 + 98 * S], 6 * S, fill=None, outline=(70, 56, 44), width=S)

        def engraved(xy, text, f, anchor):
            x, y = xy
            d.text((x + S, y + 1.5 * S), text, font=f, fill=(8, 6, 5), anchor=anchor)
            d.text((x - 0.6 * S, y - 0.8 * S), text, font=f, fill=(250, 220, 160), anchor=anchor)
            d.text((x, y), text, font=f, fill=(196, 146, 70), anchor=anchor)
        engraved((cx, y0 + 30 * S), ci[0], fnum, "mm")
        spaced = "  ".join(ci[1])
        engraved((cx, y0 + 62 * S), f"{spaced}", fit, "mm")
        engraved((cx, y0 + 83 * S), ci[2], fru, "mm")
    arr = np.asarray(img).astype(np.float32) / 255
    alpha = 1 - win
    out = np.dstack([arr, alpha])
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


if __name__ == "__main__":
    for m in range(3):
        build(m).save(f"../out/frame_{m + 1}.webp", quality=92, method=6)
        print("frame", m + 1, flush=True)
