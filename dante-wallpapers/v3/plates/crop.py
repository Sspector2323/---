"""Вырезает живопись из присланных карточек (без их рамок и медальонов) под окна триптиха."""
import json, sys
from PIL import Image, ImageFilter, ImageDraw

WIN_W, WIN_H = 608, 880
ASPECT = WIN_W / WIN_H
# (центр по x, верх, низ) в пикселях исходника 928x1152
CROPS = {1: (520, 74, 1104), 2: (430, 100, 1104), 3: (470, 130, 1104), 4: (470, 125, 1104), 5: (464, 122, 1100),
         6: (464, 172, 1104), 7: (464, 100, 1104), 8: (464, 118, 1104), 9: (464, 108, 1104)}
OUTW, OUTH = WIN_W * 2, WIN_H * 2

for k, (cx, y0, y1) in CROPS.items():
    im = Image.open(f"src_art/circle_{k}.jpg").convert("RGB")
    h = y1 - y0; w = h * ASPECT
    if w > 840:
        w = 840; hh = w / ASPECT; y0 = y1 - hh
    x0 = min(max(cx - w / 2, 44), 884 - w)
    box = (x0, y0, x0 + w, y1)
    big = im.resize((OUTW, OUTH), Image.LANCZOS, box=box)
    big = big.filter(ImageFilter.UnsharpMask(radius=2.2, percent=60, threshold=2))
    big.save(f"out/plate_{k}.webp", quality=92, method=6)
    if "--grid" in sys.argv:
        g = big.resize((WIN_W, WIN_H)); d = ImageDraw.Draw(g)
        for i in range(1, 10):
            d.line([(i * WIN_W / 10, 0), (i * WIN_W / 10, WIN_H)], fill=(0, 255, 0)); d.text((i * WIN_W / 10 + 2, 2), f".{i}", fill=(0, 255, 0))
            d.line([(0, i * WIN_H / 10), (WIN_W, i * WIN_H / 10)], fill=(255, 0, 255)); d.text((2, i * WIN_H / 10 + 2), f".{i}", fill=(255, 0, 255))
        g.save(f"/tmp/claude-0/-home-user----/65625290-5a5d-5afa-9f9a-fe397295f663/scratchpad/g{k}.png")
    print(k, [round(v) for v in box])
