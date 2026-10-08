"""Собирает папки обоев (Lively / Wallpaper Engine / браузер) из движка и картинок."""
import json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DIST = os.path.join(HERE, "dist")
engine = open(os.path.join(HERE, "engine/inferno2.js"), encoding="utf-8").read()
spec = open(os.path.join(OUT, "spec.json"), encoding="utf-8").read()
ASSETS = [f"plate_{i}.webp" for i in range(1, 10)] + ["front_9.webp", "frame_1.webp", "frame_2.webp", "frame_3.webp"]

TPL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inferno — {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<style>html,body{{margin:0;height:100%;background:#070605;overflow:hidden}}canvas{{display:block}}</style>
</head><body><canvas id="inferno"></canvas>
<script>window.INFERNO_CONFIG={config};window.INFERNO_SPEC={spec};window.INFERNO_ASSETS="assets/";</script>
<script>
{engine}
</script></body></html>
"""
VARIANTS = [("inferno-monitor-1", "1", "Монитор 1 · круги I–III"), ("inferno-monitor-2", "2", "Монитор 2 · круги IV–VI"),
            ("inferno-monitor-3", "3", "Монитор 3 · круги VII–IX"), ("inferno-span", "all", "Все 3 монитора одним холстом (Span)"),
            ("inferno-single", "auto", "Один монитор · показывает круги, где сейчас поэты")]
IDX = {"1": 0, "2": 1, "3": 2, "all": 3, "auto": 4}
shutil.rmtree(DIST, ignore_errors=True)
for folder, screen, desc in VARIANTS:
    d = os.path.join(DIST, folder); os.makedirs(os.path.join(d, "assets"))
    for a in ASSETS:
        shutil.copy(os.path.join(OUT, a), os.path.join(d, "assets", a))
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(TPL.format(title=desc, config=json.dumps({"screen": screen, "cycle": 540, "fps": 30}), spec=spec, engine=engine))
    json.dump({"AppVersion": "2.0.0.0", "Title": f"Inferno — {desc}", "Desc": "Девять кругов Ада Данте в готическом триптихе. Данте и Вергилий проходят весь спуск за 9 минут; мониторы синхронны.",
               "Author": "Dante wallpapers", "License": "", "Contact": "", "Type": 1, "FileName": "index.html", "Arguments": None, "IsAbsolutePath": False},
              open(os.path.join(d, "LivelyInfo.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"screen": {"type": "dropdown", "value": IDX[screen], "text": "Какие круги показывать", "items": ["Монитор 1: I–III", "Монитор 2: IV–VI", "Монитор 3: VII–IX", "Все 9 (span)", "Авто: где поэты"]},
               "cycle": {"type": "slider", "value": 9, "min": 5, "max": 15, "step": 1, "text": "Длина спуска, минут"},
               "quotes": {"type": "checkbox", "value": True, "text": "Цитаты из «Комедии»"},
               "fps": {"type": "slider", "value": 30, "min": 15, "max": 60, "step": 5, "text": "FPS"}},
              open(os.path.join(d, "LivelyProperties.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"title": f"Inferno — {desc}", "type": "web", "file": "index.html",
               "general": {"properties": {"screen": {"order": 1, "text": "Какие круги", "type": "combo", "value": screen, "options": [{"label": l, "value": v} for l, v in [("Монитор 1: I–III", "1"), ("Монитор 2: IV–VI", "2"), ("Монитор 3: VII–IX", "3"), ("Все 9 (span)", "all"), ("Авто", "auto")]]},
                                          "cycle": {"order": 2, "text": "Длина спуска, минут", "type": "slider", "value": 9, "min": 5, "max": 15, "step": 1},
                                          "quotes": {"order": 3, "text": "Цитаты", "type": "bool", "value": True}}}},
              open(os.path.join(d, "project.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    shutil.make_archive(os.path.join(DIST, folder), "zip", d)
print("ok")
