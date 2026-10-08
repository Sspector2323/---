"""Обои 3 — «Взгляд со дна»: из ледяного Коцита вверх сквозь девять кругов к звёздам."""
import math
import sys
import numpy as np
from PIL import Image, ImageDraw
from common import *

rng = np.random.default_rng(34)
VX, VY = W * 0.585, H * 0.40   # где в небе «дыра» наверх
D1 = 165.0                      # радиус выхода к звёздам
DN = 1250.0                     # дальше этого радиуса — ледяные стены Коцита вокруг нас

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
dx, dy = xx - VX, yy - VY
d = np.hypot(dx, dy) + 1e-3
theta = np.arctan2(dy, dx)

# неровные скальные края: возмущаем глубину шумом по углу
rough = periodic_noise(theta, np.log(d) * 3, rng, terms=30, max_n=70, z_scale=4, falloff=1.0)
t_raw = np.log(DN / d) / math.log(DN / D1) + 0.018 * rough   # <0 — лёд вокруг, 1 — небо
t = np.clip(t_raw, 0, 1)
tw = t ** 0.92
twist = theta + 1.6 * tw + 0.25 * np.sin(tw * 9)        # воронка закручена
k = tw * 9.0
ring = np.clip(np.floor(k), 0, 8).astype(np.int32)       # 0 = IX (ближний) … 8 = I
f = k - np.floor(k)                                      # положение внутри уступа

# палитры: тёмный -> светлый, порядок от IX (ближний) к I (дальний)
DARK = np.array([(14, 30, 48), (28, 8, 22), (45, 6, 4), (40, 12, 2), (6, 22, 22),
                 (34, 22, 6), (14, 20, 12), (32, 6, 28), (26, 26, 36)], np.float32) / 255
LIGHT = np.array([(170, 225, 250), (175, 70, 110), (250, 85, 25), (255, 150, 45),
                  (70, 130, 105), (200, 150, 60), (120, 130, 80), (200, 90, 170),
                  (175, 175, 205)], np.float32) / 255
EMIT = np.array([0.25, 0.25, 0.9, 1.0, 0.15, 0.35, 0.15, 0.35, 0.25], np.float32)

# текстура скалы: вертикальные прожилки + крупные пятна
n_streak = periodic_noise(twist, f * 2.0, rng, terms=36, max_n=220, z_scale=1.0, falloff=0.6)
n_blob = periodic_noise(twist, tw * 40, rng, terms=30, max_n=40, z_scale=10, falloff=1.2)
n_fine = periodic_noise(twist * 1, tw * 160, rng, terms=30, max_n=500, z_scale=30, falloff=0.4)
tex = 0.5 + 0.55 * n_streak + 0.45 * n_blob + 0.25 * n_fine

# профиль уступа: тень под карнизом, стена светлеет вверх, яркая кромка
wall = np.clip(f, 0, 1) ** 0.7
lip = np.exp(-((1 - f) / 0.035) ** 2) * 1.4
under = np.clip(f / 0.08, 0, 1) ** 2
shade = (0.12 + 0.88 * wall) * under

dark, light = DARK[ring], LIGHT[ring]
amt = np.clip(shade * tex, 0, 1.3) ** 1.6 * 0.75
col = dark + (light - dark) * amt[..., None]
col += light * lip[..., None] * (0.35 + 0.6 * EMIT[ring])[..., None]
# ледяная пещера вокруг (t_raw < 0)
icez = np.clip(-t_raw * 3.5, 0, 1)
icetex = np.clip(0.3 + 0.7 * n_streak + 0.35 * n_blob + 0.2 * n_fine, 0, 1.2) ** 1.8
icecol = np.array([0.015, 0.03, 0.06]) + np.array([0.16, 0.30, 0.42]) * icetex[..., None] * (1 - icez[..., None] * 0.75)
# тень-провал у края бездны
rim_sh = np.exp(-((t_raw + 0.03) / 0.035) ** 2)
icecol *= (1 - 0.6 * rim_sh)[..., None]
col = col * (1 - np.clip(-t_raw * 30, 0, 1)[..., None]) + icecol * np.clip(-t_raw * 30, 0, 1)[..., None]

# особенности кругов
# VIII — десять рвов (полосы), VII — огненный дождь, VI — гробницы-огни, II — вихрь
sub = k * 10 % 1.0
col[ring == 1] *= (0.65 + 0.35 * np.cos(sub[ring == 1] * 2 * np.pi))[..., None]
fire_spots = np.clip(periodic_noise(twist, tw * 90, rng, terms=24, max_n=90, z_scale=40, falloff=0.8) * 3 - 0.9, 0, 1)
for r_i, amt in ((3, 1.6), (2, 1.0)):
    m = ring == r_i
    col[m] += (fire_spots[m] * amt)[..., None] * np.array([1.0, 0.45, 0.1]) * (0.3 + f[m])[..., None]
whirl = periodic_noise(twist * 1 + tw * 30, f, rng, terms=30, max_n=80, z_scale=2, falloff=0.7)
m = ring == 7
col[m] += (np.clip(whirl[m] * 2.5, 0, 1) * 0.5)[..., None] * np.array([1.0, 0.45, 0.85])
# IX — лёд: холодные блики
m = ring == 0
col[m] += (np.clip(n_fine[m] * 3 - 0.8, 0, 1) * 0.35)[..., None] * np.array([0.7, 0.9, 1.0])

# свет снизу (огни) и сверху (небо), туман глубины
fire_glow = np.exp(-((tw - 0.33) / 0.16) ** 2)
col += fire_glow[..., None] * np.array([0.30, 0.07, 0.02]) * (0.5 + 0.5 * f)[..., None]
sky_light = np.exp(-((1 - tw) / 0.10) ** 2)
col += sky_light[..., None] * np.array([0.25, 0.30, 0.45])
fog = np.clip(tw ** 2.2, 0, 1)
col = col * (1 - 0.5 * fog[..., None]) + fog[..., None] * np.array([0.20, 0.09, 0.13]) * 0.45
col *= 0.85

# ---------- небо в отверстии ----------
inside = d < D1
sky = np.zeros((H, W, 3), np.float32)
sky += np.array([0.02, 0.04, 0.10])
sky += np.exp(-(d / D1) ** 2)[..., None] * np.array([0.05, 0.10, 0.22])
stars = np.zeros((H, W), np.float32)
ii = rng.integers(0, H * W, 60000)
stars.flat[ii] = rng.uniform(0, 1, ii.size) ** 6
stars = to_f(blur(to_img(np.repeat(stars[..., None], 3, -1)), 0.7))[..., 0] * 3
sky += stars[..., None]
starimg = Image.new("RGB", (W, H))
ds = ImageDraw.Draw(starimg)
for sx, sy, s in ((-38, -70, 7), (10, 52, 6), (-62, 8, 5), (44, -18, 5.5)):  # «quattro stelle»
    x, y = VX + sx, VY + sy
    ds.ellipse([x - s, y - s, x + s, y + s], fill=(255, 250, 235))
starglow = glow(starimg, radii=(2, 6, 18), weights=(1.0, 0.8, 0.5))
sky += starglow * 1.2
edge = np.clip((D1 - d) / 4, 0, 1)[..., None]
col = col * (1 - edge) + sky * edge
# светящийся обод выхода
halo = np.exp(-((d - D1) / 22) ** 2) * (d > D1 - 3) + np.exp(-((d - D1) / 140) ** 2) * 0.35
col += halo[..., None] * np.array([0.55, 0.62, 0.8])

# ---------- угли, летящие вверх (штрихи к центру) ----------
emb = Image.new("RGB", (W, H))
de = ImageDraw.Draw(emb)
for _ in range(650):
    a = rng.uniform(-math.pi, math.pi)
    r = DN * math.exp(-rng.uniform(0.05, 0.85) * math.log(DN / D1))
    L = r * rng.uniform(0.015, 0.06)
    x0, y0 = VX + r * math.cos(a), VY + r * math.sin(a)
    x1, y1 = VX + (r - L) * math.cos(a + 0.01), VY + (r - L) * math.sin(a + 0.01)
    c = (255, int(rng.uniform(110, 210)), int(rng.uniform(30, 80)))
    de.line([x0, y0, x1, y1], fill=c, width=int(rng.choice([1, 2, 2, 3])))
col += glow(emb, radii=(2, 8, 24), weights=(0.8, 0.5, 0.3)) * 0.9

# ---------- иней Коцита по краям кадра ----------
fr = fbm(H // 2, W // 2, rng, octaves=7, base=6, persistence=0.6)
fr = np.asarray(Image.fromarray(fr, mode="F").resize((W, H), Image.BICUBIC))
ex = np.minimum(xx, W - xx) / W; ey = np.minimum(yy, H - yy) / H
edgeness = np.clip(1 - np.minimum(ex * 7.0, ey * 5.0), 0, 1)
frost = np.clip((fr * 0.8 + edgeness * 0.9 - 1.0) * 3, 0, 1) ** 1.5 * 0.6
crys = Image.new("RGB", (W, H))
dc = ImageDraw.Draw(crys)
for _ in range(2500):  # иглы инея
    x, y = rng.uniform(0, W), rng.uniform(0, H)
    e = 1 - min(min(x, W - x) / W * 7.0, min(y, H - y) / H * 5.0)
    if e < rng.uniform(0.4, 1.0):
        continue
    L = rng.uniform(6, 34) * e
    a0 = rng.uniform(0, math.pi / 3)
    for j in range(3):
        a = a0 + j * math.pi / 3
        dc.line([x - L * math.cos(a), y - L * math.sin(a), x + L * math.cos(a), y + L * math.sin(a)],
                fill=(90, 130, 160), width=1)
cry = to_f(crys)
ice = np.array([0.72, 0.86, 0.95])
col = col * (1 - frost[..., None] * 0.75) + ice * frost[..., None] * 0.55
col += cry * 0.35 + to_f(blur(crys, 6)) * 0.25

# ---------- подпись ----------
tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
dt = ImageDraw.Draw(tl)
dt.text((300, H - 330), "e quindi uscimmo a riveder le stelle", font=font(SERIF_IT, 54), fill=(225, 235, 250, 235))
dt.text((302, H - 262), "…и здесь мы вышли вновь узреть светила.   Inferno, XXXIV, 139", font=font(FREE_IT, 30), fill=(170, 190, 210, 200))
la = np.asarray(tl, np.float32) / 255
txt_glow = to_f(blur(Image.fromarray((la[..., :3] * la[..., 3:] * 255).astype(np.uint8)), 10)) * 0.6
col = col * (1 - la[..., 3:]) + la[..., :3] * la[..., 3:] + txt_glow

col = 1 - np.exp(-np.clip(col, 0, None) * 1.15)
col = vignette(col, 0.45)
col = film_grain(col, rng, 0.015)
to_img(col).save(sys.argv[1] if len(sys.argv) > 1 else "../03_abyss.png", optimize=True)
print("ok")
