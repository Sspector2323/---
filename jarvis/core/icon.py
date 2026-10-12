"""Значок Джарвиса (трей, уведомления) — рисуется кодом при первом запуске."""
from . import config


def icon_path(size: int = 256):
    path = config.DATA_DIR / "jarvis.png"
    if path.exists():
        return path
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    c, r = size / 2, size * 0.36
    d.ellipse([c - r, c - r, c + r, c + r], outline=(56, 217, 255, 255), width=int(size * 0.07))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.04))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.ellipse([c - r, c - r, c + r, c + r], outline=(160, 240, 255, 255), width=int(size * 0.035))
    rc = size * 0.14
    d.ellipse([c - rc, c - rc, c + rc, c + rc], fill=(220, 250, 255, 255))
    img.save(path)
    return path
