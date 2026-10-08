"""Общие помощники для генерации обоев «Ад Данте»."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 3840, 2160
FONT_DIR = "/usr/share/fonts/truetype/"
SERIF = FONT_DIR + "crosextra/Caladea-Regular.ttf"
SERIF_IT = FONT_DIR + "crosextra/Caladea-Italic.ttf"
SERIF_B = FONT_DIR + "crosextra/Caladea-Bold.ttf"
FREE = FONT_DIR + "freefont/FreeSerif.ttf"
FREE_IT = FONT_DIR + "freefont/FreeSerifItalic.ttf"
FREE_B = FONT_DIR + "freefont/FreeSerifBold.ttf"

CIRCLES = [
    ("I", "LIMBO", "Лимб"),
    ("II", "LUSSURIA", "Сладострастие"),
    ("III", "GOLA", "Чревоугодие"),
    ("IV", "AVARIZIA", "Скупость"),
    ("V", "IRA", "Гнев"),
    ("VI", "ERESIA", "Ересь"),
    ("VII", "VIOLENZA", "Насилие"),
    ("VIII", "FRODE", "Обман"),
    ("IX", "TRADIMENTO", "Предательство"),
]


def font(path, size):
    return ImageFont.truetype(path, int(size))


def to_f(img):
    return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0


def to_img(arr):
    return Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))


def blur(img, r):
    return img.filter(ImageFilter.GaussianBlur(r))


def glow(img, radii=(3, 10, 30, 80), weights=(1.0, 0.8, 0.6, 0.45)):
    """Неоновое свечение: исходник + несколько размытых копий (аддитивно)."""
    base = to_f(img)
    out = base.copy()
    for r, w in zip(radii, weights):
        out += to_f(blur(img, r)) * w
    return out


def screen(a, b):
    return 1 - (1 - a) * (1 - b)


def text_on_circle(img, text, cx, cy, r, center_angle, fnt, fill, spacing=1.0,
                   outward=True):
    """Пишет текст по дуге окружности. center_angle — угол центра надписи (рад,
    0 = вправо, по часовой стрелке в экранных координатах)."""
    widths = [fnt.getlength(ch) * spacing for ch in text]
    total = sum(widths)
    arc = total / r
    # для текста «снаружи сверху» идём по часовой; внизу — против, чтобы читался
    direction = 1 if outward else -1
    a = center_angle - direction * arc / 2
    for ch, w in zip(text, widths):
        mid = a + direction * (w / 2) / r
        if ch.strip():
            asc, desc = fnt.getmetrics()
            tile = Image.new("RGBA", (int(w / spacing) + 8, asc + desc + 8), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((4, 4), ch, font=fnt, fill=fill)
            rot = -math.degrees(mid) - 90 if outward else -math.degrees(mid) + 90
            tile = tile.rotate(rot, resample=Image.BICUBIC, expand=True)
            x = cx + r * math.cos(mid) - tile.width / 2
            y = cy + r * math.sin(mid) - tile.height / 2
            img.alpha_composite(tile, (int(x), int(y)))
        a += direction * w / r


def periodic_noise(theta, z, rng, terms=28, max_n=60, z_scale=6.0, falloff=1.1):
    """Гладкий шум, периодичный по углу theta (сумма синусоид)."""
    out = np.zeros_like(theta, dtype=np.float32)
    total = 0.0
    for _ in range(terms):
        n = int(rng.integers(1, max_n))
        m = rng.uniform(-1, 1) * z_scale * n / 6
        ph = rng.uniform(0, 2 * np.pi)
        amp = 1.0 / (n ** (falloff * 0.5))
        out += amp * np.sin(n * theta + m * z + ph).astype(np.float32)
        total += amp
    return out / total


def film_grain(arr, rng, amount=0.025):
    g = rng.normal(0, amount, arr.shape[:2]).astype(np.float32)[..., None]
    return arr + g


def vignette(arr, strength=0.65, power=2.2):
    yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]].astype(np.float32)
    nx = (xx / arr.shape[1] - 0.5) * 2
    ny = (yy / arr.shape[0] - 0.5) * 2
    d = np.sqrt(nx ** 2 * 0.8 + ny ** 2)
    v = 1 - strength * np.clip(d / 1.5, 0, 1) ** power
    return arr * v[..., None]


def fbm(h, w, rng, octaves=6, base=4, persistence=0.55):
    """Фрактальный шум (облака/дым) через увеличение случайных сеток."""
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gh, gw = base * 2 ** o, int(base * 2 ** o * w / h) + 1
        g = rng.random((gh, gw)).astype(np.float32)
        layer = np.asarray(Image.fromarray(g, mode="F").resize((w, h), Image.BICUBIC))
        out += layer * amp
        total += amp
        amp *= persistence
    return out / total


SINNERS = [
    "некрещёные и праведные язычники",
    "унесённые вихрем страсти",
    "лежат под ледяным грязным дождём",
    "скупцы и моты катят камни",
    "гневные дерутся в болоте Стикс",
    "еретики в огненных гробницах",
    "кровавая река, лес, огненный песок",
    "десять рвов Злых Щелей",
    "вмёрзшие в озеро Коцит",
]
