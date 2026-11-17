"""Картинка-карточка трека 1280×720: размытая обложка, винил, название, бейджи и путь трека
YouTube → Скачано → Google Диск → ВКонтакте. Перерисовывается на каждом этапе."""
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONTS = Path(__file__).resolve().parent / "fonts"
W, H = 1280, 720
GOLD = (226, 190, 120)
GOLD_SOFT = (226, 190, 120, 60)
GREEN = (88, 214, 141)
RED = (240, 96, 96)
WHITE = (245, 242, 236)
MUTED = (190, 184, 172)
DIM = (120, 116, 110)

STEPS = ["YouTube", "Скачано", "Google Диск", "ВКонтакте"]
# этап карточки → (сколько шагов готово, активный шаг, подпись-чип, цвет чипа)
STAGES = {
    "queue": (0, 0, "В ОЧЕРЕДИ", GOLD),
    "download": (1, 1, "КАЧАЮ", GOLD),
    "upload": (2, 2, "ЗАГРУЖАЮ НА ДИСК", GOLD),
    "ready": (3, 3, "ГОТОВО · ЖДЁТ ВК", GOLD),
    "work": (3, 3, "ВЫКЛАДЫВАЮТ В ВК", GOLD),
    "done": (4, -1, "ВЫЛОЖЕНО В ВК", GREEN),
    "error": (1, 1, "ОШИБКА", RED),
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}.otf"), size)


_SUPPORTED = re.compile(r"[^ -~ -ÿЀ-џ‐-‧‰-›№←-↓₽]")


def _clean(text: str) -> str:
    """Только символы, которые есть в шрифте (иероглифы, эмодзи и т.п. — убираем)."""
    return re.sub(r"\s{2,}", " ", _SUPPORTED.sub("", text or "")).strip(" -—|·")


def _trim(img: Image.Image) -> Image.Image:
    """Срезать чёрные поля превью YouTube (letterbox)."""
    gray = img.convert("L").point(lambda v: 255 if v > 28 else 0)
    box = gray.getbbox()
    return img.crop(box) if box and (box[2] - box[0]) > 80 and (box[3] - box[1]) > 80 else img


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= width:
            cur = test
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _pill(draw, x, y, text, font, fg, bg, outline=None, pad=(18, 9)) -> int:
    tw = draw.textlength(text, font=font)
    h = font.size + pad[1] * 2
    draw.rounded_rectangle((x, y, x + tw + pad[0] * 2, y + h), radius=h // 2, fill=bg, outline=outline, width=2)
    draw.text((x + pad[0], y + pad[1] - 2), text, font=font, fill=fg)
    return int(x + tw + pad[0] * 2)


def _check(draw, cx, cy, r, color, width=5):
    draw.line([(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)],
              fill=color, width=width, joint="curve")


def render(cover: bytes | None, *, title: str, artist: str = "", badges: list[str] | None = None,
           tags: list[str] | None = None, stage: str = "queue", note: str = "", sender: str = "",
           step_notes: dict[int, str] | None = None) -> bytes:
    done, active, chip, chip_color = STAGES.get(stage, STAGES["queue"])
    try:
        art = _trim(Image.open(io.BytesIO(cover)).convert("RGB")) if cover else None
    except Exception:
        art = None
    if art is None:
        art = Image.new("RGB", (480, 480), (40, 34, 28))

    # фон: размытая обложка + затемнение + виньетка
    bg = ImageOps.fit(art, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(38))
    canvas = bg.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (8, 8, 10, 175))
    canvas.alpha_composite(shade)
    grad = Image.new("L", (W, 1))
    for x in range(W):
        grad.putpixel((x, 0), int(40 + 110 * x / W))
    canvas.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [grad.resize((W, H))]))
    d = ImageDraw.Draw(canvas)

    # винил, выглядывающий из-за обложки
    S, ax, ay = 400, 64, 92
    disc_c = (ax + S // 2 + 150, ay + S // 2)
    R = S // 2 - 6
    d.ellipse((disc_c[0] - R, disc_c[1] - R, disc_c[0] + R, disc_c[1] + R), fill=(14, 14, 16))
    for rr in range(R - 8, 60, -9):
        d.ellipse((disc_c[0] - rr, disc_c[1] - rr, disc_c[0] + rr, disc_c[1] + rr), outline=(40, 40, 46), width=1)
    label = art.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
    d.ellipse((disc_c[0] - 62, disc_c[1] - 62, disc_c[0] + 62, disc_c[1] + 62), fill=label)
    d.ellipse((disc_c[0] - 8, disc_c[1] - 8, disc_c[0] + 8, disc_c[1] + 8), fill=(14, 14, 16))
    d.arc((disc_c[0] - R + 14, disc_c[1] - R + 14, disc_c[0] + R - 14, disc_c[1] + R - 14), 300, 350,
          fill=(90, 90, 96), width=3)  # блик

    # обложка с тенью и скруглением
    sq = ImageOps.fit(art, (S, S), Image.LANCZOS)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S, S), radius=26, fill=255)
    shadow = Image.new("RGBA", (S + 80, S + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((40, 50, S + 40, S + 50), radius=30, fill=(0, 0, 0, 170))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)), (ax - 40, ay - 40))
    canvas.paste(sq, (ax, ay), mask)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((ax, ay, ax + S, ay + S), radius=26, outline=(255, 255, 255, 40), width=2)

    # правая колонка
    x0, xmax = 700, W - 60
    f_chip = _font("Inter-SemiBold", 20)
    _pill(d, x0, 92, chip, f_chip, (16, 14, 12), chip_color)
    if sender:
        f_from = _font("Inter-Medium", 22)
        s = _clean(f"прислал {sender}")
        d.text((xmax - d.textlength(s, font=f_from), 100), s, font=f_from, fill=MUTED)

    title = _clean(title) or "Трек"
    y = 150
    for size in (60, 52, 44):
        f_title = _font("InterDisplay-Black", size)
        lines = _wrap(d, title, f_title, xmax - x0, 3)
        if len(lines) <= 2 or size == 44:
            break
    for line in lines:
        d.text((x0, y), line, font=f_title, fill=WHITE)
        y += int(f_title.size * 1.08)
    if artist := _clean(artist):
        f_artist = _font("Inter-SemiBold", 30)
        d.text((x0, y + 6), _wrap(d, artist, f_artist, xmax - x0, 1)[0], font=f_artist, fill=GOLD)
        y += 52
    y += 18
    f_badge = _font("Inter-SemiBold", 20)
    x = x0
    for b in [_clean(b) for b in (badges or []) if _clean(b)]:
        if x + d.textlength(b, font=f_badge) + 40 > xmax:
            break
        x = _pill(d, x, y, b, f_badge, WHITE, (38, 36, 34), outline=(92, 88, 82), pad=(14, 7)) + 10
    if badges:
        y += 52
    tag_line = "  ".join("#" + re.sub(r"[^\w]+", "", _clean(t).lower()) for t in (tags or []) if _clean(t))
    if tag_line:
        f_tag = _font("Inter-Medium", 22)
        d.text((x0, y + 4), _wrap(d, tag_line, f_tag, xmax - x0, 1)[0], font=f_tag, fill=DIM)

    # путь трека
    py, left, right = 600, 120, W - 120
    gap = (right - left) / (len(STEPS) - 1)
    f_step = _font("Inter-SemiBold", 22)
    f_note = _font("Inter-Medium", 18)
    for i in range(len(STEPS) - 1):
        xa, xb = left + gap * i + 30, left + gap * (i + 1) - 30
        color = GREEN if i < done - 1 or (done == 4) else (GOLD if i == done - 1 and active == done else (70, 70, 74))
        d.line([(xa, py), (xb, py)], fill=color, width=4)
    for i, name in enumerate(STEPS):
        cx = left + gap * i
        if i < done:
            d.ellipse((cx - 24, py - 24, cx + 24, py + 24), fill=GREEN)
            _check(d, cx, py, 22, (12, 30, 18))
        elif i == active:
            ring = RED if stage == "error" else GOLD
            d.ellipse((cx - 34, py - 34, cx + 34, py + 34), outline=tuple(int(c * 0.55) for c in ring), width=6)
            d.ellipse((cx - 24, py - 24, cx + 24, py + 24), fill=ring)
            d.ellipse((cx - 8, py - 8, cx + 8, py + 8), fill=(16, 14, 12))
        else:
            d.ellipse((cx - 24, py - 24, cx + 24, py + 24), outline=(90, 90, 96), width=3)
        col = WHITE if i <= max(done - 1, active) else DIM
        d.text((cx - d.textlength(name, font=f_step) / 2, py + 38), name, font=f_step, fill=col)
        sub = _clean((step_notes or {}).get(i, ""))
        if i == active and note:
            sub = _clean(note)
        if sub:
            d.text((cx - d.textlength(sub, font=f_note) / 2, py + 68), sub, font=f_note,
                   fill=(RED if stage == "error" else GOLD) if i == active else MUTED)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()
