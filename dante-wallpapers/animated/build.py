"""Собирает готовые обои: по папке на монитор + превью на все три.
Каждая папка — самодостаточная (index.html со встроенным движком) и подходит
для Lively Wallpaper (LivelyInfo.json) и Wallpaper Engine (project.json)."""
import json, os, shutil, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
engine = open(os.path.join(HERE, "src/inferno.js"), encoding="utf-8").read()
tpl = open(os.path.join(HERE, "src/template.html"), encoding="utf-8").read()
DIST = os.path.join(HERE, "dist")
shutil.rmtree(DIST, ignore_errors=True)
os.makedirs(DIST)

VARIANTS = [
    ("inferno-monitor-1", "1", "Монитор 1 · круги I–III"),
    ("inferno-monitor-2", "2", "Монитор 2 · круги IV–VI"),
    ("inferno-monitor-3", "3", "Монитор 3 · круги VII–IX"),
    ("inferno-span", "all", "Растянуть на 3 монитора (Span) · все 9 кругов"),
    ("inferno-single", "auto", "Один монитор · показывает круги, где сейчас поэты"),
]
SCREEN_IDX = {"1": 0, "2": 1, "3": 2, "all": 3, "auto": 4}

for folder, screen, desc in VARIANTS:
    out = os.path.join(DIST, folder)
    os.makedirs(out)
    html = (tpl.replace("%TITLE%", desc)
               .replace("%CONFIG%", json.dumps({"screen": screen, "cycle": 540, "fps": 30, "labels": 1}))
               .replace("%ENGINE%", engine))
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    # Lively Wallpaper
    json.dump({
        "AppVersion": "2.0.0.0", "Title": f"Inferno — {desc}",
        "Desc": "Девять кругов Ада Данте. Данте и Вергилий проходят весь спуск за 9 минут, потом цикл повторяется. Три монитора идут синхронно по системным часам.",
        "Author": "Dante wallpapers", "License": "", "Contact": "", "Type": 1,
        "FileName": "index.html", "Arguments": None, "IsAbsolutePath": False,
    }, open(os.path.join(out, "LivelyInfo.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({
        "screen": {"type": "dropdown", "value": SCREEN_IDX[screen], "text": "Какие круги показывать",
                   "items": ["Монитор 1: I–III", "Монитор 2: IV–VI", "Монитор 3: VII–IX", "Все 9 (span)", "Авто: где поэты"]},
        "cycle": {"type": "slider", "value": 9, "min": 5, "max": 15, "step": 1, "text": "Длина спуска, минут"},
        "labels": {"type": "checkbox", "value": True, "text": "Подписи кругов и цитаты"},
        "fps": {"type": "slider", "value": 30, "min": 15, "max": 60, "step": 5, "text": "FPS (меньше — тише видеокарта)"},
    }, open(os.path.join(out, "LivelyProperties.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # Wallpaper Engine (web wallpaper)
    json.dump({
        "title": f"Inferno — {desc}", "type": "web", "file": "index.html", "preview": "preview.jpg",
        "general": {"properties": {
            "screen": {"order": 1, "text": "Какие круги", "type": "combo", "value": screen,
                       "options": [{"label": "Монитор 1: I–III", "value": "1"}, {"label": "Монитор 2: IV–VI", "value": "2"},
                                   {"label": "Монитор 3: VII–IX", "value": "3"}, {"label": "Все 9 (span)", "value": "all"},
                                   {"label": "Авто", "value": "auto"}]},
            "cycle": {"order": 2, "text": "Длина спуска, минут", "type": "slider", "value": 9, "min": 5, "max": 15, "step": 1},
            "labels": {"order": 3, "text": "Подписи", "type": "bool", "value": True},
        }},
    }, open(os.path.join(out, "project.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("built:", ", ".join(v[0] for v in VARIANTS))
