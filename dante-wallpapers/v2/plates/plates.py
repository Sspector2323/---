"""Фоновые картины для девяти окон триптиха (по 1120x1860, виртуально 560x930).
Запуск: python3 plates.py [номера сцен]  ->  ../out/plate_N.webp (+ front_N.webp, spec.json)"""
import json
import math
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from paint import *

PATH_Y = 878          # по этой линии идут Данте и Вергилий
SPEC = {}             # координаты, общие с анимацией


def rock_height(seed, sx=1.0, sy=1.0):
    t = noise(seed, octaves=7, base=6, pers=0.58, sx=sx, sy=sy)
    r = 1 - np.abs(noise(seed + 1, octaves=6, base=10, sx=sx, sy=sy) * 2 - 1)
    return t * 0.6 + r * 0.4


def ledge(img, seed, albedo, lights, ambient, y=PATH_Y + 2, amp=6, rimcol=None):
    """Передний скальный карниз, по которому идут поэты."""
    line = line1d(seed, y, amp, n_ctrl=10)
    m = below(line)
    h = rock_height(seed + 3, 1.6, 1) + np.clip((YV - line[None, :]) / 25, 0, 1) * -0.6
    img = material(img, m, albedo, h, lights, ambient, 9)
    if rimcol is not None:
        img += rim(m, 0, -1, 1.3)[..., None] * np.asarray(rimcol)
    return img


def ridge_layer(img, seed, base, amp, albedo, lights, ambient, fogcol, fogk, n_ctrl=6, strength=6, rimcol=None):
    m = below(line1d(seed, base, amp, n_ctrl))
    h = rock_height(seed + 7)
    img = material(img, m, albedo, h, lights, ambient, strength)
    img = lay(img, m * fogk, fogcol)
    if rimcol is not None:
        img += rim(m, 0, -1, 1.2)[..., None] * np.asarray(rimcol)
    return img


def clouds(img, seed, col, lights, ambient, y0=0, y1=500, k=0.6, sx=3):
    h = noise(seed, octaves=7, base=3, pers=0.6, sx=sx)
    dens = np.clip((h - 0.42) * 2.4, 0, 1) * np.clip((y1 - YV) / 120, 0, 1) * np.clip((YV - y0) / 60, 0, 1)
    lit = light(normals(h, 30), lights, ambient)
    return img * (1 - (dens * k)[..., None]) + (np.asarray(col) * lit) * (dens * k)[..., None]


# ======================================================================
def limbo():
    L = [("point", 280, 470, 60, C(255, 238, 200) * 2.2, 260)]
    img = vgrad([(0, C(5, 7, 12)), (0.3, C(14, 19, 28)), (0.55, C(40, 46, 54)), (0.62, C(30, 34, 38)), (1, C(8, 10, 10))])
    img = clouds(img, 11, C(70, 76, 90), L, C(20, 22, 30) / 255 * 3, 30, 520, 0.7, sx=4)
    dome = np.clip(1 - ((XV - 280) / 250) ** 2 - ((YV - 545) / 235) ** 2, 0, 1) * (YV < 548)
    img += (blurm(dome, 14) ** 1.3)[..., None] * C(160, 150, 120) * 0.5
    img = glow(img, 280, 465, 60, C(255, 238, 200), 1.1)
    img = glow(img, 280, 470, 210, C(140, 140, 120), 0.35)
    for i, (b, a, fk) in enumerate([(528, 18, 0.62), (548, 22, 0.35)]):
        img = ridge_layer(img, 3 + i * 10, b, a, C(60, 66, 74), L, C(16, 18, 22) / 255 * 4, C(56, 62, 70), fk, rimcol=C(120, 115, 90) * 0.4)
    # замок о семи стенах
    polys = []
    for i in range(7):
        w = 236 - i * 28; h = 26 + i * 15; y = 556 - h; x0 = 280 - w / 2
        pts = [(x0, 556), (x0, y)]
        n = int(w / 12)
        for j in range(n):
            xa = x0 + j * w / n
            if j % 2 == 0:
                pts += [(xa, y), (xa, y - 5), (xa + w / n, y - 5), (xa + w / n, y)]
        pts += [(x0 + w, y), (x0 + w, 556)]
        polys.append(pts)
        for tx in (x0 + 5, x0 + w - 5):
            polys.append([(tx - 6, 556), (tx - 6, y - 14), (tx, y - 30), (tx + 6, y - 14), (tx + 6, 556)])
    polys.append([(268, 556), (268, 396), (280, 360), (292, 396), (292, 556)])
    cm = poly_mask(polys, 0.45)
    bricks = (np.sin(YV * 1.6) > 0.85) * 0.25 + noise(7, octaves=5, base=20) * 0.6
    img = material(img, cm, C(70, 72, 78), bricks, [("point", 280, 420, -40, C(255, 230, 180) * 0.6, 200)], C(18, 20, 24) / 255 * 3, 4)
    img += rim(cm, 0, -1, 1.4)[..., None] * C(255, 232, 180) * 0.85
    rng = np.random.default_rng(4)
    for _ in range(30):
        x = 280 + rng.uniform(-100, 100); y = rng.uniform(450, 548)
        if cm[int(y * S), int(x * S)] > 0.9:
            img = glow(img, x, y, 1.4, C(255, 210, 140), 1.0, falloff=3)
    # луг в перспективе, освещённый замком
    u, v, z = ground_uv(560, k=90)
    g = tsample(tex(12, base=8), u * 0.6, v * 3.0)
    gh = tsample(tex(13, base=24, ridged=True), u * 1.5, v * 6)
    meadow = below(line1d(9, 562, 4, 8))
    alb = C(52, 66, 54) * (0.5 + 0.8 * g)[..., None]
    img = material(img, meadow, alb, gh * 0.6 + g, L + [("dir", -0.3, -1, 0.6, C(40, 50, 60) / 255)], C(14, 18, 18) / 255 * 3, 3)
    # ручей отражает купол света
    stream = np.clip(1 - np.abs(YV - 574 - 5 * np.sin(XV / 45)) / 3.2, 0, 1) * np.clip(1 - np.abs(XV - 280) / 280, 0, 1)
    img = reflect(img, 556, stream, tsample(tex(14, base=30), u * 4, v * 0.6), 2, (0.85, 0.9, 1.0), 0.8)
    img = fog(img, 552, 640, C(110, 116, 120), 0.6, 21, sx=8)
    img = fog(img, 660, 800, C(60, 70, 74), 0.4, 22, sx=9)
    img = ledge(img, 30, C(60, 64, 62), [("dir", 0.1, -1, 0.4, C(70, 72, 70) / 255 * 1.6)] + L, C(10, 12, 12) / 255 * 3, rimcol=C(150, 150, 130) * 0.4)
    SPEC["limbo"] = {"light": [280, 470]}
    return finish(img, 1, exposure=1.05, lift=(0.008, 0.01, 0.016))


def lussuria():
    LT = [("point", 340, 170, 160, C(255, 150, 230) * 2.4, 320), ("point", 280, 820, 60, C(255, 90, 170) * 1.2, 200)]
    img = vgrad([(0, C(6, 1, 9)), (0.35, C(30, 6, 34)), (0.7, C(22, 5, 22)), (1, C(8, 2, 7))])
    base = fbm(PH // 2, PW // 2, 31, octaves=7, base=3, pers=0.6)
    cx, cy = 280, 420
    r = np.hypot(XV - cx, (YV - cy) * 1.5) + 1
    a = np.arctan2((YV - cy) * 1.5, XV - cx) + 2.4 * np.exp(-r / 260)
    ch = sample(base, (cx + r * np.cos(a)) * S / 2, (cy + r * np.sin(a) / 1.5) * S / 2)
    dens = np.clip((ch - 0.4) * 2.4, 0, 1)
    lit = light(normals(ch, 40), LT, C(30, 10, 34) / 255 * 3)
    img = img * (1 - dens[..., None] * 0.8) + (C(110, 50, 110) * lit) * dens[..., None] * 0.8
    img = glow(img, 340, 170, 90, C(255, 170, 240), 0.5)
    # смерч: цилиндрическое освещение + закрученные полосы
    cxf = 280 + 22 * np.sin(YV / 140)
    hw = 30 + np.clip(880 - YV, 0, 900) * 0.24 + 6 * np.sin(YV / 30)
    s = (XV - cxf) / np.maximum(hw, 1)
    funnel = np.clip((1 - np.abs(s)) * hw / 4, 0, 1) * np.clip((890 - YV) / 30, 0, 1)
    ang = np.arcsin(np.clip(s, -1, 1))
    streak = tsample(tex(33, base=6), (ang * 160 + YV * 1.4) * 2, YV * 0.5)
    shade = (0.35 + 0.65 * np.cos(ang - 0.5)) * (0.5 + 0.9 * streak)
    fcol = C(84, 26, 80) * shade[..., None] + (np.abs(s) ** 6)[..., None] * C(255, 130, 210) * 0.7
    img = lay(img, funnel * 0.88, fcol)
    img = glow(img, 280, 845, 80, C(255, 90, 170), 0.45, sy=0.35)
    # обломки скал — «la ruina»
    rng = np.random.default_rng(7)
    polys = []; x = -20
    while x < 600:
        w = rng.uniform(40, 110); h = rng.uniform(30, 120)
        n = 14; cxr = x + w / 2; top = 884 - h
        pts = [(cxr + w / 2 * math.cos(t) * (1 + 0.12 * math.sin(t * 5 + w)), 930 - (930 - top) * max(0, math.sin(t)) * (1 + 0.08 * math.cos(t * 7))) for t in np.linspace(0, math.pi, n)]
        polys.append(pts)
        x += w * 0.8
    rocks = poly_mask(polys, 0.5)
    img = material(img, rocks, C(70, 50, 70), rock_height(41), LT, C(10, 4, 10) / 255 * 3, 10)
    img += rim(rocks, 0.2, -1, 1.4)[..., None] * C(255, 140, 220) * 0.6
    img = ledge(img, 44, C(60, 40, 60), LT, C(8, 3, 8) / 255 * 3, rimcol=C(255, 130, 210) * 0.4)
    SPEC["lussuria"] = {"vortex": [280, 160, 880]}
    return finish(img, 2, exposure=1.1)


def gola():
    LT = [("dir", -0.5, -1, 0.7, C(120, 130, 110) / 255 * 1.4)]
    img = vgrad([(0, C(8, 10, 8)), (0.4, C(28, 32, 26)), (0.57, C(52, 54, 44)), (0.6, C(30, 28, 20)), (1, C(8, 7, 5))])
    img = clouds(img, 51, C(60, 66, 56), LT, C(20, 22, 18) / 255 * 3, 0, 520, 0.8, sx=3)
    for i, (b, a, fk) in enumerate([(518, 14, 0.55), (538, 18, 0.3)]):
        img = ridge_layer(img, 52 + i * 5, b, a, C(60, 62, 50), LT, C(14, 15, 12) / 255 * 3, C(48, 52, 44), fk)
    u, v, z = ground_uv(556, k=90)
    hgt = tsample(tex(55, base=6), u, v * 2) * 0.7 + tsample(tex(56, base=30, ridged=True), u * 2, v * 4) * 0.3
    mud = below(line1d(54, 556, 3, 8))
    img = material(img, mud, C(78, 66, 44) * (0.6 + 0.6 * tsample(tex(57, base=10), u, v))[..., None], hgt, LT, C(14, 13, 10) / 255 * 3, 4)
    # лужи отражают небо
    pud = np.clip((tsample(tex(58, base=7), u * 0.8, v * 2.5) - 0.6) * 12, 0, 1) * mud
    img = reflect(img, 556, pud, tsample(tex(59, base=40), u * 6, v * 0.5), 1.5, (0.8, 0.85, 0.8), 0.75)
    # скала Цербера
    rock = poly_mask([[(300, 712), (316, 668), (356, 645), (420, 640), (468, 660), (500, 704), (508, 770), (292, 770)]], 0.5)
    rock *= below(line1d(57, 645, 8, 6))
    img = material(img, rock, C(70, 72, 56), rock_height(60), LT, C(10, 10, 8) / 255 * 3, 10)
    img += rim(rock, -0.4, -1, 1.3)[..., None] * C(160, 175, 130) * 0.5
    img = fog(img, 540, 625, C(70, 74, 64), 0.5, 61, sx=8)
    rain = noise(62, octaves=4, base=50, sx=0.1, sy=8)
    img += np.clip((rain - 0.55) * 3, 0, 1)[..., None] * C(90, 96, 86) * 0.1
    img = ledge(img, 63, C(66, 58, 42), LT, C(10, 9, 7) / 255 * 3, rimcol=C(150, 160, 120) * 0.3)
    SPEC["gola"] = {"cerberus": [400, 646]}
    return finish(img, 3, exposure=1.08)


def avarizia():
    LT = [("dir", 0.2, -1, 0.5, C(255, 200, 120) / 255 * 1.7), ("point", 300, 520, 40, C(255, 190, 100) * 1.0, 260)]
    img = vgrad([(0, C(12, 7, 3)), (0.35, C(58, 36, 12)), (0.56, C(150, 104, 44)), (0.58, C(96, 64, 26)), (1, C(16, 10, 4))])
    img = clouds(img, 70, C(150, 100, 50), LT, C(40, 24, 10) / 255 * 3, 0, 500, 0.6, sx=5)
    img = shafts(img, 300, -60, C(255, 200, 120), 0.1, 71, n=16, spread=0.3)
    img = glow(img, 300, 525, 300, C(255, 190, 100), 0.25, sy=0.25)
    crowd = noise(73, octaves=4, base=70, sx=0.2, sy=1)
    band = np.exp(-((YV - 530) / 6) ** 2)
    img = img * (1 - (np.clip((crowd - 0.45) * 3, 0, 1) * band * 0.75)[..., None])
    u, v, z = ground_uv(536, k=100)
    hgt = tsample(tex(75, base=8), u, v * 1.5) * 0.6 + tsample(tex(76, base=40, ridged=True), u * 3, v * 3) * 0.4
    plain = below(line1d(74, 536, 2, 4))
    img = material(img, plain, C(150, 104, 52) * (0.6 + 0.6 * tsample(tex(77, base=12), u, v))[..., None], hgt, LT, C(24, 16, 8) / 255 * 3, 5)
    img = lay(img, plain * np.clip(1 - (YV - 536) / 80, 0, 1) * 0.7, C(170, 120, 60))
    crag = poly_mask([[(0, 610), (0, 296), (30, 276), (72, 330), (98, 410), (124, 520), (156, 610)]], 0.5)
    img = material(img, crag, C(110, 80, 46), rock_height(78, 0.7, 1.5), LT, C(16, 10, 5) / 255 * 3, 10)
    img += rim(crag, 0.6, -1, 1.5)[..., None] * C(255, 200, 120) * 0.7
    pl = poly_mask([[(24, 284), (28, 250), (36, 236), (32, 220), (44, 210), (54, 224), (52, 240), (62, 262), (58, 286)]], 0.35)
    img = lay(img, pl, C(10, 5, 2))
    img += rim(pl, 0.6, -1, 1.1)[..., None] * C(255, 180, 100) * 0.8
    img = fog(img, 520, 610, C(170, 120, 60), 0.45, 79, sx=8)
    img = ledge(img, 80, C(120, 84, 44), LT, C(16, 10, 5) / 255 * 3, rimcol=C(255, 200, 120) * 0.35)
    return finish(img, 4, exposure=1.0)


def ira():
    LT = [("point", 442, 398, 30, C(255, 120, 40) * 1.6, 220), ("dir", 0, -1, 0.4, C(60, 110, 110) / 255 * 0.9)]
    img = vgrad([(0, C(3, 7, 9)), (0.4, C(12, 26, 28)), (0.58, C(28, 50, 48)), (0.6, C(16, 32, 32)), (1, C(3, 8, 8))])
    img = clouds(img, 81, C(40, 70, 70), LT, C(10, 20, 22) / 255 * 3, 0, 520, 0.65, sx=4)
    tower = poly_mask([[(420, 560), (424, 420), (416, 410), (468, 410), (460, 420), (464, 560)]], 0.45)
    img = material(img, tower, C(40, 50, 50), noise(82, octaves=5, base=24), [("point", 442, 390, 40, C(255, 120, 40) * 2, 60)], C(6, 12, 12) / 255 * 3, 3)
    img += rim(tower, 0, -1, 1.2)[..., None] * C(255, 140, 70) * 0.6
    img = glow(img, 442, 398, 70, C(255, 120, 40), 0.35)
    far = poly_mask([[(70, 556), (72, 500), (88, 500), (90, 556)]], 0.5)
    img = lay(img, far * 0.7, C(10, 20, 20))
    img = glow(img, 80, 494, 24, C(255, 120, 40), 0.25)
    img = ridge_layer(img, 83, 551, 8, C(30, 50, 48), LT, C(6, 12, 12) / 255 * 3, C(26, 46, 46), 0.3)
    u, v, z = ground_uv(556, k=90)
    rip = tsample(tex(84, base=30), u * 2, v * 0.35)
    water = np.clip((YV - 556) * S, 0, 1)
    img = reflect(img, 556, water, rip, 4, (0.55, 0.8, 0.78), 0.92)
    img = lay(img, water * np.clip((YV - 556) / 380, 0, 1) * 0.7, C(4, 12, 12))
    rl = light(normals(tsample(tex(85, base=40), u * 3, v * 0.5), 6), LT, 0)
    img += (rl * water[..., None]) * C(40, 70, 70) * 0.4
    rng = np.random.default_rng(85)
    polys = []
    for _ in range(10):
        x = rng.uniform(0, 560); y = rng.uniform(600, 820); h = rng.uniform(18, 60) * (y - 520) / 250
        polys.append([(x - 2.5, y), (x - 1, y - h), (x + rng.uniform(-9, 9), y - h * 1.15), (x + 2, y - h), (x + 3, y)])
    img = lay(img, poly_mask(polys, 0.35), C(3, 8, 8))
    img = fog(img, 540, 650, C(56, 88, 84), 0.5, 86, sx=10)
    img = fog(img, 720, 840, C(30, 52, 50), 0.35, 87, sx=10)
    img = ledge(img, 88, C(40, 54, 50), LT, C(5, 9, 9) / 255 * 3, rimcol=C(120, 180, 170) * 0.35)
    SPEC["ira"] = {"water": 556, "beacon": [442, 398], "far": [80, 494]}
    return finish(img, 5, exposure=1.12)


def eresia():
    rng = np.random.default_rng(92)
    tombs = []
    for y, sc, n in [(600, 0.42, 7), (646, 0.58, 6), (716, 0.8, 4), (806, 1.05, 3)]:
        for i in range(n):
            x = (i + 0.5 + (rng.random() - 0.5) * 0.35) * 560 / n
            tombs.append([round(float(x), 1), y, sc])
    LT = [("point", x, y - 30 * sc, 30 * sc, C(255, 110, 30) * 0.9 * sc, 90 * sc) for x, y, sc in tombs]
    LT += [("point", 280, 470, 80, C(255, 70, 20) * 1.0, 300)]
    img = vgrad([(0, C(6, 1, 1)), (0.3, C(26, 5, 3)), (0.45, C(70, 14, 5)), (0.6, C(26, 7, 4)), (1, C(6, 2, 1))])
    img = clouds(img, 91, C(110, 40, 20), [("point", 280, 520, 50, C(255, 90, 30) * 2, 300)], C(20, 6, 4) / 255 * 3, 0, 440, 0.75, sx=3)
    polys = [[(0, 562), (0, 430)] + sum([[(x, 430), (x, 421), (x + 9, 421), (x + 9, 430)] for x in range(0, 560, 18)], []) + [(560, 430), (560, 562)]]
    for x in (40, 130, 220, 340, 430, 520):
        w = rng.uniform(26, 40); h = rng.uniform(70, 150); top = 430 - h
        arc = [(x + w / 2 * math.cos(a), top - w / 2 * math.sin(a)) for a in np.linspace(0, math.pi, 14)]
        polys.append([(x + w / 2, 562), (x + w / 2, top)] + arc + [(x - w / 2, top), (x - w / 2, 562)])
    walls = poly_mask(polys, 0.45)
    brick = ((np.sin(YV * 1.3) > 0.8) | (np.sin(XV * 0.55 + (np.floor(YV * 1.3 / math.pi) % 2) * 1.6) > 0.93)) * 0.3
    hot = noise(93, octaves=6, base=6, sx=1.5)
    emis = C(255, 60, 12) * (hot ** 2 * 0.9 + 0.15)[..., None] * np.clip((YV - 330) / 230, 0.2, 1.2)[..., None]
    img = material(img, walls, C(90, 40, 30), noise(94, octaves=5, base=30) * 0.5 - brick, LT[-1:], C(20, 6, 4) / 255 * 3, 5)
    img += walls[..., None] * emis * 0.6
    img += rim(walls, 0, -1, 1.3)[..., None] * C(255, 150, 70) * 0.8
    gate = poly_mask([[(258, 562), (258, 500), (280, 474), (302, 500), (302, 562)]], 0.4)
    img = lay(img, gate, C(8, 2, 1))
    img = glow(img, 280, 480, 270, C(255, 80, 20), 0.2, sy=0.5)
    u, v, z = ground_uv(560, k=90)
    gh = tsample(tex(95, base=10), u, v * 2) * 0.6 + tsample(tex(96, base=40, ridged=True), u * 3, v * 4) * 0.4
    ground = below(line1d(97, 560, 2, 4))
    img = material(img, ground, C(80, 50, 40) * (0.6 + 0.6 * tsample(tex(98, base=10), u, v))[..., None], gh, LT, C(14, 6, 4) / 255 * 3, 4)
    stone = noise(99, octaves=6, base=20)
    for x, y, sc in tombs:
        w, h, d = 74 * sc, 22 * sc, 14 * sc
        side = poly_mask([[(x + w / 2, y), (x + w / 2 + 8 * sc, y - 6 * sc), (x + w / 2 + 8 * sc, y - h - 6 * sc), (x + w / 2, y - h)]], 0.3)
        front = poly_mask([[(x - w / 2, y), (x + w / 2, y), (x + w / 2, y - h), (x - w / 2, y - h)]], 0.3)
        inner = poly_mask([[(x - w / 2 + 3 * sc, y - h), (x + w / 2 - 3 * sc, y - h), (x + w / 2 + 4 * sc, y - h - d), (x - w / 2 + 6 * sc, y - h - d)]], 0.3)
        img = lay(img, side, C(30, 12, 8) * (0.6 + 0.6 * stone)[..., None])
        img = lay(img, front, C(70, 34, 24) * (0.55 + 0.7 * stone)[..., None])
        img += front[..., None] * np.clip(1 - (y - YV) / (h + 1), 0, 1)[..., None] * 0
        img += rim(front, 0, -1, 1.1)[..., None] * C(255, 170, 90) * 0.9
        img = lay(img, inner, C(255, 170, 70))
        img = glow(img, x, y - h - d * 0.5, 30 * sc, C(255, 110, 30), 0.6)
        lid = poly_mask([[(x - w / 2 - 6 * sc, y + 2 * sc), (x - w / 2 - 2 * sc, y - h - 8 * sc), (x - w / 2 + 6 * sc, y - h - 10 * sc), (x - w / 2 + 2 * sc, y + 2 * sc)]], 0.3)
        img = lay(img, lid, C(48, 22, 16) * (0.6 + 0.6 * stone)[..., None])
        img += rim(lid, 1, -0.3, 1)[..., None] * C(255, 140, 60) * 0.6
    img = fog(img, 545, 625, C(130, 44, 16), 0.35, 100, sx=8)
    img = ledge(img, 101, C(90, 50, 36), LT, C(10, 4, 3) / 255 * 3, rimcol=C(255, 130, 60) * 0.45)
    SPEC["eresia"] = {"tombs": tombs}
    return finish(img, 6, exposure=1.05)


def violenza():
    LT = [("point", 280, 330, -30, C(255, 120, 30) * 2.2, 380), ("point", 280, 900, 40, C(255, 40, 20) * 1.2, 220)]
    img = vgrad([(0, C(8, 2, 1)), (0.25, C(36, 7, 3)), (0.36, C(180, 66, 16)), (0.4, C(120, 44, 12)), (0.5, C(60, 18, 6)), (1, C(8, 2, 2))])
    img = clouds(img, 100, C(130, 40, 14), [("point", 280, 380, 40, C(255, 110, 30) * 2, 300)], C(20, 4, 2) / 255 * 3, 0, 330, 0.75, sx=4)
    img = glow(img, 280, 345, 260, C(255, 120, 30), 0.35, sy=0.22)
    u, v, z = ground_uv(342, k=60)
    dunes = tsample(tex(101, base=5), u * 0.5, v * 2.2)
    sand = np.clip((YV - 343) * S, 0, 1) * np.clip((530 - YV) / 20, 0, 1)
    img = material(img, sand, C(200, 100, 40), dunes, [("dir", 0, -1, 0.3, C(255, 150, 60) / 255 * 1.2)], C(40, 12, 4) / 255 * 3, 14)
    img = glow(img, 280, 360, 200, C(255, 140, 50), 0.18, sy=0.2)
    im = Image.new("L", (PW, PH), 0); d = ImageDraw.Draw(im)
    rng = np.random.default_rng(102)

    def br(x, y, a, l, w, depth):
        if depth == 0 or l < 3:
            return
        bend = rng.uniform(-0.4, 0.4)
        xm = x + math.cos(a) * l * 0.5; ym = y + math.sin(a) * l * 0.5
        x2 = xm + math.cos(a + bend) * l * 0.5; y2 = ym + math.sin(a + bend) * l * 0.5
        for (p, q) in (((x, y), (xm, ym)), ((xm, ym), (x2, y2))):
            d.line([p[0] * S, p[1] * S, q[0] * S, q[1] * S], fill=255, width=max(1, int(w * S)))
            d.ellipse([(q[0] - w / 2) * S, (q[1] - w / 2) * S, (q[0] + w / 2) * S, (q[1] + w / 2) * S], fill=255)
        for _ in range(2 if depth > 2 else 3):
            br(x2, y2, a + bend + rng.uniform(-0.9, 0.9), l * rng.uniform(0.55, 0.8), w * 0.66, depth - 1)
        if rng.random() < 0.7:
            d.line([x2 * S, y2 * S, (x2 + rng.uniform(-7, 7)) * S, (y2 + rng.uniform(-7, 7)) * S], fill=255, width=S)

    trees = []
    for yb, sc, n in [(548, 0.55, 10), (630, 0.8, 7), (730, 1.15, 4)]:
        for i in range(n):
            x = (i + rng.uniform(0.1, 0.9)) * 560 / n
            trees.append([round(float(x), 1), yb, sc])
            br(x, yb + 12, -math.pi / 2 + rng.uniform(-0.3, 0.3), 72 * sc, 13 * sc, 7)
    forest = np.asarray(im.filter(ImageFilter.GaussianBlur(0.45 * S)), np.float32) / 255
    ground = below(line1d(103, 524, 5, 6))
    gh = rock_height(104)
    img = material(img, ground, C(70, 30, 20), gh, LT, C(10, 3, 2) / 255 * 3, 6)
    img = fog(img, 500, 600, C(130, 44, 16), 0.45, 105, sx=6)
    bark = noise(106, octaves=5, base=30, sx=0.4, sy=2)
    img = lay(img, forest, C(18, 7, 6) * (0.6 + 0.8 * bark)[..., None])
    img += rim(forest, 0, -1, 1.1)[..., None] * C(255, 120, 40) * 0.75
    img = fog(img, 640, 750, C(70, 20, 10), 0.35, 107, sx=7)
    # Флегетон — кипящая кровь
    u2, v2, z2 = ground_uv(560, k=100)
    rip = tsample(tex(108, base=30), u2 * 2, v2 * 0.4)
    river = np.clip((YV - 742) * S, 0, 1)
    img = reflect(img, 742, river, rip, 3, (1.0, 0.25, 0.18), 0.65)
    img = lay(img, river * 0.55, C(110, 6, 6) * (0.6 + 0.8 * rip)[..., None])
    img += (np.clip(rip - 0.6, 0, 1) * 3 * river * np.exp(-(YV - 742) / 70))[..., None] * C(255, 120, 80) * 0.5
    img = fog(img, 735, 790, C(160, 50, 40), 0.4, 109, sx=8)
    img = ledge(img, 110, C(90, 36, 24), LT, C(10, 3, 2) / 255 * 3, rimcol=C(255, 90, 50) * 0.5)
    SPEC["violenza"] = {"sand": [345, 520], "river": [742, 870], "trees": trees}
    return finish(img, 7, exposure=1.05)


def malebolge():
    VPX, HOR = 280, 262
    glows = [C(120, 80, 170), C(170, 90, 40), C(50, 140, 90), C(170, 50, 40), C(80, 100, 170), C(170, 130, 60)]
    img = vgrad([(0, C(3, 2, 6)), (0.22, C(18, 10, 30)), (0.28, C(44, 28, 66)), (0.3, C(14, 9, 22)), (1, C(4, 2, 6))])
    img = clouds(img, 111, C(60, 40, 90), [("point", 280, 240, 40, C(180, 120, 255) * 2, 200)], C(10, 6, 16) / 255 * 3, 0, 262, 0.6, sx=4)
    img = glow(img, 280, 262, 180, C(170, 110, 255), 0.3, sy=0.2)
    u, v, z = ground_uv(HOR, cx=VPX)
    stone_h = tsample(tex(112, base=10), u, v) * 0.6 + tsample(tex(113, base=40, ridged=True), u * 3, v * 3) * 0.4
    lightsT = [("dir", 0, -1, 0.5, C(140, 110, 190) / 255 * 1.1), ("point", 280, 700, 30, C(255, 120, 60) * 0.5, 200)]
    groundm = np.clip((YV - HOR) * S, 0, 1)
    img = material(img, groundm, C(84, 66, 104) * (0.55 + 0.6 * stone_h)[..., None], stone_h, lightsT, C(8, 6, 14) / 255 * 3, 4)
    # рвы — полосы с тёмными стенами и цветным свечением со дна
    rows = []
    y = HOR + 10
    k = 0
    while True:
        dy = y - HOR
        hgt = 4 + dy * 0.22          # ширина рва растёт к нам
        gap = 6 + dy * 0.2
        if y + hgt > PATH_Y - 30:
            break
        g = glows[k % len(glows)]
        t = np.clip((YV - y) / hgt, 0, 1) * (YV >= y) * (YV <= y + hgt)
        inside = ((YV >= y) & (YV <= y + hgt)).astype(np.float32)
        wall = C(30, 22, 44) * (0.5 + 0.6 * stone_h)[..., None] * (0.3 + 0.7 * (1 - t))[..., None]
        floor_glow = (t ** 3)[..., None] * g * 0.45
        img = lay(img, inside, wall + floor_glow)
        img += (np.exp(-((YV - y - hgt) / (hgt * 0.5 + 1)) ** 2) * 0.18)[..., None] * g
        img += (np.abs(YV - y) < 0.6)[..., None] * C(190, 160, 240) * 0.18
        rows.append([round(float(y), 1), round(float(hgt), 1), k % len(glows)])
        y += hgt + gap
        k += 1
    # каменная дамба с арками уходит к центру
    halfw = np.maximum(YV - HOR, 0) * 0.14 + 2
    on = (np.abs(XV - VPX) < halfw) & (YV > HOR)
    dh = tsample(tex(114, base=14), (XV - VPX) / np.maximum(halfw, 1) * 40, v)
    img = material(img, on.astype(np.float32), C(110, 92, 130) * (0.6 + 0.5 * dh)[..., None], dh, lightsT, C(10, 8, 16) / 255 * 3, 3)
    edge = (np.abs(np.abs(XV - VPX) - halfw) < 0.8) & (YV > HOR)
    img += edge[..., None] * C(210, 180, 255) * 0.4
    img = fog(img, HOR - 10, HOR + 140, C(60, 40, 90), 0.5, 115, sx=6)
    img = ledge(img, 116, C(84, 66, 104), lightsT, C(8, 6, 14) / 255 * 3, rimcol=C(200, 160, 255) * 0.35)
    SPEC["malebolge"] = {"hor": HOR, "vpx": VPX, "rows": rows, "glows": [[int(c * 255) for c in g] for g in glows]}
    return finish(img, 8, exposure=1.15)


def tradimento():
    img = vgrad([(0, C(2, 4, 8)), (0.35, C(9, 20, 33)), (0.6, C(38, 66, 88)), (0.64, C(80, 118, 138)), (1, C(14, 30, 44))])
    img = clouds(img, 120, C(60, 90, 120), [("point", 280, 380, 60, C(140, 200, 255) * 1.6, 300)], C(8, 14, 22) / 255 * 3, 0, 560, 0.6, sx=4)
    img = glow(img, 280, 380, 220, C(120, 180, 230), 0.26)
    for x, h, w in ((50, 300, 70), (520, 330, 80)):
        g = poly_mask([[(x - w / 2, 600), (x - w / 2 + 6, 600 - h + 50), (x - 18, 600 - h + 20), (x, 600 - h), (x + 18, 600 - h + 20), (x + w / 2 - 6, 600 - h + 50), (x + w / 2, 600)]], 1.5)
        img = lay(img, g * 0.55, C(14, 28, 40))
    img = fog(img, 420, 600, C(60, 90, 110), 0.45, 121, sx=6)
    SPEC["tradimento"] = {"ice": 596, "lucifer": [280, 300]}
    back = finish(img, 9, exposure=1.1)

    # передний слой: лёд Коцита (закрывает пояс Люцифера). Полупрозрачен у горизонта —
    # сквозь него анимация рисует отражение Люцифера.
    u, v, z = ground_uv(596, k=100)
    itex = tsample(tex(122, base=10), u, v * 1.5)
    cracks = tsample(tex(123, base=14, ridged=True), u * 1.4, v * 1.4)
    cr = np.clip((cracks - 0.93) * 18, 0, 1)
    ice = np.clip((YV - 596) * S, 0, 1)
    icol = vgrad([(0.64, C(160, 200, 220)), (0.72, C(80, 120, 145)), (1, C(16, 34, 50))]) * (0.75 + 0.45 * itex)[..., None]
    icol = icol * (1 - 0.35 * light(normals(itex, 6), [("dir", 0, -1, 0.6, C(255, 255, 255) / 255)], 0)[..., :1] * 0)
    icol += cr[..., None] * C(220, 245, 255) * 0.45 * np.clip((YV - 600) / 120, 0, 1)[..., None]
    sheen = np.exp(-((XV - 280) / 80) ** 2) * np.clip(1 - (YV - 600) / 260, 0, 1)
    icol += sheen[..., None] * C(130, 180, 220) * 0.35
    hz = np.exp(-((YV - 598) / 16) ** 2)
    alpha = np.clip(ice * np.clip(0.55 + (YV - 596) / 140, 0, 1) + hz * 0.8, 0, 1)
    col = icol * ice[..., None] + C(160, 200, 225) * (hz * (1 - ice))[..., None]
    col = 1 - np.exp(-np.clip(col, 0, None) * 1.6)
    rgba = np.dstack([np.clip(col, 0, 1), alpha])
    front = Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA")
    return back, front


SCENES = [limbo, lussuria, gola, avarizia, ira, eresia, violenza, malebolge, tradimento]

if __name__ == "__main__":
    which = [int(a) for a in sys.argv[1:]] or list(range(1, 10))
    for i in which:
        res = SCENES[i - 1]()
        back, front = res if isinstance(res, tuple) else (res, None)
        back.save(f"../out/plate_{i}.webp", quality=90, method=6)
        if front:
            front.save(f"../out/front_{i}.webp", quality=90, method=6)
        print("plate", i, flush=True)
    try:
        old = json.load(open("../out/spec.json"))
    except Exception:
        old = {}
    old.update(SPEC)
    json.dump(old, open("../out/spec.json", "w"), indent=1)
