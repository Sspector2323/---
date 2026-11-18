"""Готовит живопись из присланных карточек: целиком внутреннюю картину (без рамок и медальонов)
и запоминает, какую её часть показывало «стандартное» окно 608x880 (по нему размечены эффекты)."""
import json
from PIL import Image, ImageFilter

WIN_W, WIN_H = 608, 880
ASPECT = WIN_W / WIN_H
AX0, AX1 = 44, 884                     # картина без рамки по горизонтали (исходник 928x1152)
# (центр по x, верх, низ) — верх отрезает медальон с номером
CROPS = {1: (520, 74, 1104), 2: (430, 100, 1104), 3: (470, 130, 1104), 4: (470, 125, 1104), 5: (464, 122, 1100),
         6: (464, 172, 1104), 7: (464, 100, 1104), 8: (464, 118, 1104), 9: (464, 108, 1104)}
SCALE = 2.0
spec = {}
for k, (cx, y0, y1) in CROPS.items():
    im = Image.open(f"src_art/circle_{k}.jpg").convert("RGB")
    h = y1 - y0; w = h * ASPECT
    x0 = min(max(cx - w / 2, AX0), AX1 - w)
    art = (AX0, y0, AX1, y1)
    big = im.resize((round((AX1 - AX0) * SCALE), round(h * SCALE)), Image.LANCZOS, box=art)
    big = big.filter(ImageFilter.UnsharpMask(radius=2.2, percent=60, threshold=2))
    big.save(f"out/art_{k}.webp", quality=92, method=6)
    # стандартное окно в долях картины
    spec[k] = {"aspect": (AX1 - AX0) / h, "win": [(x0 - AX0) / (AX1 - AX0), 0.0, w / (AX1 - AX0), 1.0]}
    print(k, big.size, [round(v, 3) for v in spec[k]["win"]])
json.dump(spec, open("out/art_spec.json", "w"), indent=1)
