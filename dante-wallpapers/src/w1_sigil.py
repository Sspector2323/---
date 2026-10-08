"""Обои 1 — «Сигил»: девять кругов как светящаяся неоновая печать (вид сверху)."""
import math
import sys
import numpy as np
from PIL import Image, ImageDraw
from common import *

S = 2  # рисуем в 2x, потом уменьшаем — сглаживание
CX, CY = W * S // 2, H * S // 2
rng = np.random.default_rng(9)

R = [1000, 905, 815, 730, 650, 575, 500, 400, 255, 140]  # границы I..IX, центр
R = [r * S for r in R]
COL = [(175, 170, 225), (255, 60, 180), (170, 235, 60), (255, 200, 60),
       (40, 225, 205), (255, 120, 30), (255, 45, 45), (190, 80, 255), (120, 220, 255)]
GAP_A = -math.pi / 2  # сектор для подписей — строго вверх

lines = Image.new("RGB", (W * S, H * S), (0, 0, 0))
d = ImageDraw.Draw(lines)
labels = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))


def P(r, a):
    return (CX + r * math.cos(a), CY + r * math.sin(a))


def angdist(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


gap = {}


def in_gap(a, r, ring):
    return angdist(a, GAP_A) < gap[ring] * (R[ring] / max(r, 1)) * 0.5 + 0.02


def arc(r, a0, a1, col, w=3, steps=None):
    steps = steps or max(8, int(abs(a1 - a0) * r / 6))
    pts = [P(r, a0 + (a1 - a0) * i / steps) for i in range(steps + 1)]
    d.line(pts, fill=col, width=w)


def ring_circle(r, col, w=3, ring=None, dash=None):
    """Окружность с пропуском в секторе подписей."""
    n = int(2 * math.pi * r / 6)
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        if (ring is not None and in_gap(a, r, ring)) or (dash and (i // dash) % 2):
            if len(pts) > 1:
                d.line(pts, fill=col, width=w)
            pts = []
            continue
        pts.append(P(r, a))
    if len(pts) > 1:
        d.line(pts, fill=col, width=w)


def dim(c, k):
    return tuple(int(v * k) for v in c)


# ---------- подписи кругов (сначала считаем ширину сектора) ----------
for i, (num, name, _) in enumerate(CIRCLES):
    rmid = (R[i] + R[i + 1]) / 2
    size = max(22, min(34, (R[i] - R[i + 1]) * 0.36 / S)) * S
    f = font(SERIF_B, size)
    txt = f"{num} · {name}"
    length = sum(f.getlength(c) * 1.25 for c in txt)
    gap[i] = length / rmid + 0.12
    text_on_circle(labels, txt, CX, CY, rmid - size * 0.35, GAP_A, f,
                   fill=COL[i] + (255,), spacing=1.25)

# ---------- границы кругов ----------
for i in range(9):
    ring_circle(R[i], dim(COL[i], 0.9), w=3 * S // 2 + 1, ring=i)
ring_circle(R[9], dim(COL[8], 0.9), w=3)

# радиальные «меридианы» по краям сектора подписей
for i in range(9):
    for s in (-1, 1):
        a = GAP_A + s * gap[i] * 0.5
        d.line([P(R[i + 1] + 6, a), P(R[i] - 6, a)], fill=dim(COL[i], 0.6), width=2)

# ---------- I. Лимб: пунктирные круги + благородный замок о семи стенах ----------
c = COL[0]
for k in range(5):
    r = R[1] + (R[0] - R[1]) * (k + 1) / 6
    ring_circle(r, dim(c, 0.35 + 0.1 * (k % 2)), w=2, ring=0, dash=3 + k)
for _ in range(220):
    a = rng.uniform(0, 2 * math.pi); r = rng.uniform(R[1] + 10, R[0] - 10)
    if in_gap(a, r, 0):
        continue
    x, y = P(r, a); s = rng.uniform(2, 5) * S
    d.ellipse([x - s, y - s, x + s, y + s], outline=dim(c, 0.7), width=2)
cxl, cyl = P((R[0] + R[1]) / 2, math.pi)  # замок слева
for k in range(7):
    s = (8 + k * 5) * S
    d.regular_polygon((cxl, cyl, s), 7, rotation=k * 6, outline=dim(c, 1 - k * 0.08), width=2)

# ---------- II. Сладострастие: вихрь ----------
c = COL[1]
for _ in range(260):
    a0 = rng.uniform(0, 2 * math.pi)
    L = rng.uniform(0.12, 0.45)
    r0 = rng.uniform(R[2] + 12, R[1] - 12)
    amp = rng.uniform(4, 16) * S
    ph = rng.uniform(0, 6.28)
    pts = []
    for t in np.linspace(0, 1, 30):
        a = a0 + t * L
        r = r0 + amp * math.sin(ph + t * 7) * t
        if in_gap(a, r, 1):
            break
        pts.append(P(r, a))
    if len(pts) > 2:
        d.line(pts, fill=dim(c, rng.uniform(0.45, 1.0)), width=int(rng.choice([2, 3, 4])))

# ---------- III. Чревоугодие: град, грязный дождь, снег ----------
c = COL[2]
for _ in range(1100):
    a = rng.uniform(0, 2 * math.pi); r = rng.uniform(R[3] + 8, R[2] - 8)
    if in_gap(a, r, 2):
        continue
    x, y = P(r, a)
    if rng.random() < 0.7:
        L = rng.uniform(6, 16) * S
        d.line([x, y, x - L * 0.35, y + L], fill=dim(c, rng.uniform(0.35, 0.9)), width=2)
    else:
        s = rng.uniform(1.5, 3.5) * S
        d.ellipse([x - s, y - s, x + s, y + s], fill=dim(c, rng.uniform(0.4, 0.9)))
# Цербер — три точки-головы внизу
for k in (-1, 0, 1):
    x, y = P((R[2] + R[3]) / 2, math.pi / 2 + k * 0.035)
    d.ellipse([x - 9 * S, y - 9 * S, x + 9 * S, y + 9 * S], outline=(255, 255, 160), width=3)

# ---------- IV. Скупость: валуны катят навстречу друг другу ----------
c = COL[3]
rm = (R[3] + R[4]) / 2
n = 34
for k in range(n):
    a = 2 * math.pi * k / n + 0.04
    if in_gap(a, rm, 3):
        continue
    x, y = P(rm, a)
    s = 13 * S
    d.ellipse([x - s, y - s, x + s, y + s], outline=c, width=3)
    d.ellipse([x - s * 0.35, y - s * 0.35, x + s * 0.35, y + s * 0.35], fill=dim(c, 0.6))
    # стрелка: правая половина — по часовой, левая — против
    sgn = 1 if math.cos(a) > 0 else -1
    a1, a2 = a + sgn * 0.035, a + sgn * 0.075
    arc(rm, a1, a2, dim(c, 0.8), w=3)
    tip = P(rm, a2 + sgn * 0.012)
    for side in (-1, 1):
        d.line([tip, P(rm + side * 7 * S, a2 - sgn * 0.004)], fill=dim(c, 0.8), width=3)
# точка столкновения — внизу
bx, by = P(rm, math.pi / 2)
for k in range(16):
    a = k * math.pi / 8
    d.line([bx + 16 * S * math.cos(a), by + 16 * S * math.sin(a),
            bx + 34 * S * math.cos(a), by + 34 * S * math.sin(a)], fill=(255, 240, 180), width=3)
for r in (R[3] - 10 * S, R[4] + 10 * S):
    ring_circle(r, dim(c, 0.3), w=2, ring=3, dash=2)

# ---------- V. Гнев: болото Стикс ----------
c = COL[4]
for k in range(6):
    r0 = R[5] + (R[4] - R[5]) * (k + 0.8) / 7
    freq = 40 + k * 13; amp = (3 + k % 3 * 2) * S
    pts = []
    for i in range(1600):
        a = 2 * math.pi * i / 1600
        if in_gap(a, r0, 4):
            if len(pts) > 1:
                d.line(pts, fill=dim(c, 0.4 + 0.1 * k), width=2)
            pts = []
            continue
        pts.append(P(r0 + amp * math.sin(freq * a + k), a))
    if len(pts) > 1:
        d.line(pts, fill=dim(c, 0.4 + 0.1 * k), width=2)
for _ in range(160):  # пузыри — дыхание погружённых
    a = rng.uniform(0, 2 * math.pi); r = rng.uniform(R[5] + 8, R[4] - 8)
    if in_gap(a, r, 4):
        continue
    x, y = P(r, a); s = rng.uniform(2, 6) * S
    d.ellipse([x - s, y - s, x + s, y + s], outline=dim(c, 0.9), width=2)

# ---------- VI. Ересь: стены Дита + горящие гробницы ----------
c = COL[5]
# зубчатая стена города Дит по внешней границе VI
merl = 180
for k in range(merl):
    a0 = 2 * math.pi * k / merl; a1 = 2 * math.pi * (k + 1) / merl
    if in_gap(a0, R[5], 5):
        continue
    rr = R[5] - (12 * S if k % 2 else 0)
    am = (a0 + a1) / 2
    d.line([P(R[5], a0), P(rr, a0), P(rr, a1), P(R[5], a1)], fill=(255, 70, 40), width=3)
rm = (R[5] + R[6]) / 2 - 4 * S
n = 46
for k in range(n):
    a = 2 * math.pi * k / n
    if in_gap(a, rm, 5):
        continue
    hw = 0.022; h0, h1 = rm - 20 * S, rm + 6 * S
    d.polygon([P(h0, a - hw), P(h1, a - hw), P(h1, a + hw), P(h0, a + hw)], outline=c, width=3)
    # открытая крышка
    d.line([P(h1, a + hw), P(h1 + 10 * S, a + hw * 2.2)], fill=dim(c, 0.8), width=3)
    # пламя
    for j in range(3):
        aa = a - hw + hw * (0.5 + j * 0.5)
        L = rng.uniform(10, 22) * S
        d.line([P(h0, aa - 0.006), P(h0 - L, aa), P(h0, aa + 0.006)], fill=(255, 200, 80), width=2)

# ---------- VII. Насилие: Флегетон, лес самоубийц, огненный песок ----------
r_a, r_b, r_c, r_d = R[6], R[6] - 33 * S, R[6] - 67 * S, R[7]
for r0 in (r_b, r_c):
    ring_circle(r0, dim(COL[6], 0.55), w=2, ring=6)
# кипящая кровь
for k in range(4):
    r0 = r_b + (r_a - r_b) * (k + 0.5) / 4
    pts = []
    for i in range(1400):
        a = 2 * math.pi * i / 1400
        if in_gap(a, r0, 6):
            if len(pts) > 1:
                d.line(pts, fill=(255, 30 + 15 * k, 40), width=3)
            pts = []
            continue
        pts.append(P(r0 + 3 * S * math.sin(a * (70 + 9 * k) + k * 2), a))
    if len(pts) > 1:
        d.line(pts, fill=(255, 30 + 15 * k, 40), width=3)


def thorn(x, y, ang, length, depth):
    if depth == 0 or length < 2:
        return
    x2, y2 = x + length * math.cos(ang), y + length * math.sin(ang)
    d.line([x, y, x2, y2], fill=(255, 95, 60) if depth > 2 else (200, 70, 50), width=max(1, depth))
    for s in (-1, 1):
        thorn(x2, y2, ang + s * rng.uniform(0.35, 0.8), length * rng.uniform(0.55, 0.75), depth - 1)


for k in range(70):  # лес — кривые колючие деревья
    a = 2 * math.pi * k / 70 + rng.uniform(-0.02, 0.02)
    if in_gap(a, r_c, 6):
        continue
    x, y = P(r_c + 2 * S, a)
    thorn(x, y, a + math.pi + rng.uniform(-0.3, 0.3), rng.uniform(10, 15) * S, 4)
for _ in range(900):  # огненный дождь на песок
    a = rng.uniform(0, 2 * math.pi); r = rng.uniform(r_d + 6, r_c - 6)
    if in_gap(a, r, 6):
        continue
    x, y = P(r, a)
    L = rng.uniform(4, 10) * S
    d.line([x, y - L, x, y], fill=(255, 150, 40), width=2)
    d.ellipse([x - 2 * S, y - 2 * S, x + 2 * S, y + 2 * S], fill=(255, 230, 140))

# ---------- VIII. Злые щели: 10 рвов и каменные мосты ----------
c = COL[7]
for k in range(1, 10):
    r0 = R[8] + (R[7] - R[8]) * k / 10
    ring_circle(r0, dim(c, 0.75), w=2, ring=7)
for k in range(10):  # содержимое рвов, у каждого свой ритм
    r0 = R[8] + (R[7] - R[8]) * (k + 0.5) / 10
    step = 0.012 + 0.004 * (k % 4)
    a = 0
    while a < 2 * math.pi:
        if not in_gap(a, r0, 7):
            x, y = P(r0, a)
            if k % 3 == 0:
                d.ellipse([x - 2 * S, y - 2 * S, x + 2 * S, y + 2 * S], fill=dim(c, 0.9))
            elif k % 3 == 1:
                arc(r0, a, a + step * 0.5, dim(c, 0.8), w=2, steps=3)
            else:
                d.line([P(r0 - 4 * S, a), P(r0 + 4 * S, a)], fill=(255, 120, 220), width=2)
        a += step
for k in range(14):  # мосты-перемычки
    a = 2 * math.pi * k / 14 + 0.11
    if in_gap(a, (R[7] + R[8]) / 2, 7):
        continue
    for s in (-1, 1):
        d.line([P(R[8] - 4 * S, a + s * 0.008 * 400 / 330), P(R[7], a + s * 0.006)], fill=(230, 200, 255), width=2)

# ---------- IX. Коцит: великаны-башни, лёд, трещины, снежинки ----------
c = COL[8]
for k in range(12):  # великаны вокруг колодца
    a = 2 * math.pi * k / 12 + 0.26
    if in_gap(a, R[8], 8):
        continue
    d.line([P(R[8] - 2 * S, a), P(R[8] + 22 * S, a)], fill=(220, 240, 255), width=7)
    x, y = P(R[8] + 26 * S, a)
    d.ellipse([x - 5 * S, y - 5 * S, x + 5 * S, y + 5 * S], outline=(220, 240, 255), width=3)
for k in range(1, 4):  # Каина, Антенора, Птоломея, Джудекка
    ring_circle(R[9] + (R[8] - R[9]) * k / 4, dim(c, 0.5), w=2, ring=8, dash=2)
for _ in range(70):  # трещины во льду
    a = rng.uniform(0, 2 * math.pi)
    r = R[9] + 5
    pts = [P(r, a)]
    while r < R[8] - 10 * S:
        r += rng.uniform(6, 14) * S
        a += rng.uniform(-0.05, 0.05)
        pts.append(P(r, a))
    if not in_gap(a, r, 8):
        d.line(pts, fill=dim(c, rng.uniform(0.3, 0.7)), width=2)
for _ in range(60):
    a = rng.uniform(0, 2 * math.pi); r = rng.uniform(R[9] + 15 * S, R[8] - 15 * S)
    if in_gap(a, r, 8):
        continue
    x, y = P(r, a); s = rng.uniform(5, 11) * S; rot = rng.uniform(0, 1)
    for j in range(6):
        aa = rot + j * math.pi / 3
        d.line([x, y, x + s * math.cos(aa), y + s * math.sin(aa)], fill=(210, 245, 255), width=2)

# ---------- Центр: Люцифер — три пары крыльев и три лица ----------
for k in range(3):
    base = -math.pi / 2 + k * 2 * math.pi / 3 + math.pi / 3
    for side in (-1, 1):
        pts = [P(28 * S, base)]
        span = 0.95
        for j in range(5):  # перепончатый край
            t0 = j / 5; t1 = (j + 1) / 5
            a0 = base + side * span * t0; a1 = base + side * span * t1
            pts.append(P(128 * S - 18 * S * math.sin(t0 * math.pi), a0 + side * 0.02))
            pts.append(P(100 * S - 10 * S * math.sin(t1 * math.pi), (a0 + a1) / 2))
        pts.append(P(30 * S, base + side * span))
        d.line(pts + [pts[0]], fill=(225, 245, 255), width=3)
        for j in range(1, 5):  # «кости» крыла
            d.line([P(28 * S, base), P(124 * S, base + side * span * j / 5)], fill=(150, 200, 230), width=2)
for k, colf in enumerate([(255, 50, 40), (255, 245, 170), (60, 60, 80)]):
    a = -math.pi / 2 + k * 2 * math.pi / 3
    x, y = P(16 * S, a)
    d.ellipse([x - 10 * S, y - 10 * S, x + 10 * S, y + 10 * S], outline=colf, width=4)

# ---------- шкала-астролябия и надпись на вратах ----------
for k in range(360):
    a = math.radians(k)
    L = 26 if k % 10 == 0 else (14 if k % 5 == 0 else 7)
    d.line([P(R[0] + 8 * S, a), P(R[0] + (8 + L) * S, a)], fill=(110, 80, 70) if k % 10 else (200, 140, 100), width=2)
ring_circle(R[0] + 8 * S, (120, 80, 70), w=2)
gate = ["PER ME SI VA NE LA CITTÀ DOLENTE", "PER ME SI VA NE L'ETTERNO DOLORE",
        "PER ME SI VA TRA LA PERDUTA GENTE", "LASCIATE OGNE SPERANZA, VOI CH'INTRATE"]
fg = font(SERIF, 25 * S)
for txt, ang, out in zip(gate, (-150, -30, 30, 150), (True, True, False, False)):
    text_on_circle(labels, txt, CX, CY, R[0] + 52 * S, math.radians(ang), fg,
                   fill=(225, 160, 120, 230), spacing=1.18, outward=out)

# ---------- путь Данте и Вергилия: спуск, всегда налево ----------
pts = []
turns = 2.25
for t in np.linspace(0, 1, 5000):
    a = GAP_A - 0.6 - t * turns * 2 * math.pi
    r = R[0] - (R[0] - 60 * S) * (t ** 0.9)
    pts.append(P(r, a))
for i in range(0, len(pts) - 1, 7):
    d.line([pts[i], pts[i + 1]], fill=(255, 225, 150), width=3)

# ---------- сборка ----------
# легенда справа (по-русски)
lg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
dl = ImageDraw.Draw(lg)
fn, ft, fh = font(SERIF_B, 30), font(FREE_IT, 30), font(FREE, 24)
x0, y0 = 3130, 700
dl.text((x0, y0 - 70), "INFERNO", font=font(SERIF, 40), fill=(230, 170, 130, 220))
dl.line([x0, y0 - 18, x0 + 560, y0 - 18], fill=(150, 90, 80, 200), width=2)
for i, (num, name, ru) in enumerate(CIRCLES):
    y = y0 + i * 78
    dl.text((x0, y), num, font=fn, fill=COL[i] + (235,))
    dl.text((x0 + 82, y - 2), ru, font=ft, fill=(235, 220, 215, 225))
    dl.text((x0 + 82, y + 32), SINNERS[i], font=fh, fill=(170, 150, 150, 190))
dl.text((x0, y0 + 9 * 78 + 20), "· · ·  путь Данте и Вергилия — всегда налево", font=fh, fill=(255, 225, 150, 200))
labels.alpha_composite(lg.resize((W * S, H * S), Image.BICUBIC))

small = lines.resize((W, H), Image.LANCZOS)
lab = labels.resize((W, H), Image.LANCZOS)
neon = glow(small, radii=(2, 7, 22, 70), weights=(0.9, 0.7, 0.55, 0.5))

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
rr = np.hypot(xx - W / 2, yy - H / 2)
bg = np.zeros((H, W, 3), np.float32)
# тёмная воронка: к центру — багровый жар, по краям — фиолетовая ночь
heat = np.exp(-(rr / 520) ** 2)
bg += np.stack([0.10 * heat + 0.025, 0.012 * heat + 0.008, 0.03 * heat + 0.03], -1)
bg += np.stack([0.0, 0.0, 0.0], -1)
# звёздная пыль
stars = np.zeros((H, W), np.float32)
idx = rng.integers(0, H * W, 5000)
stars.flat[idx] = rng.uniform(0.15, 0.9, idx.size) ** 2
stars = to_f(blur(to_img(np.repeat(stars[..., None], 3, -1)), 0.8))[..., 0] * 2.2
bg += stars[..., None] * np.array([0.9, 0.8, 1.0]) * (rr > 1030)[..., None]

# дым и жар, поднимающиеся из воронки
smoke = fbm(H // 4, W // 4, rng, octaves=6, base=3)
smoke = np.asarray(Image.fromarray(smoke, mode="F").resize((W, H), Image.BICUBIC))
smoke = np.clip((smoke - 0.45) * 2.2, 0, 1) ** 1.6
fall = np.clip((rr - 950) / 500, 0, 1) * np.exp(-((rr - 1250) / 900) ** 2)
bg += (smoke * fall)[..., None] * np.array([0.22, 0.05, 0.10])

out = bg + neon
la = np.asarray(lab, np.float32) / 255.0
txt_rgb, alpha = la[..., :3], la[..., 3:4]
txt_glow = to_f(blur(Image.fromarray((la[..., :3] * alpha * 255).astype(np.uint8)), 6)) * 0.8
out = out * (1 - alpha) + txt_rgb * alpha + txt_glow
# тонко-тональная кривая, чтобы неон не выгорал в белый
out = 1 - np.exp(-out * 1.25)
out = vignette(out, 0.55)
out = film_grain(out, rng, 0.012)
to_img(out).save(sys.argv[1] if len(sys.argv) > 1 else "../01_sigil.png", optimize=True)
print("ok")
