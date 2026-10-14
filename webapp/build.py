"""Собирает webapp/index.html из src/template.html и картинок src/assets.json.

Запуск: python webapp/build.py  (после правок шаблона — тексты, казино, бонусы).
"""
import json
import re
from pathlib import Path

here = Path(__file__).resolve().parent
template = (here / "src" / "template.html").read_text(encoding="utf-8")
assets = json.loads((here / "src" / "assets.json").read_text(encoding="utf-8"))

html = re.sub(r"\{\{img:(\w+)\}\}", lambda m: assets[m.group(1)], template)
html = html.replace("{{LOGOS}}", json.dumps(assets["logos"]))
assert "{{" not in html, "в шаблоне остались незаполненные {{...}}"
(here / "index.html").write_text(html, encoding="utf-8")
print(f"webapp/index.html: {len(html) // 1024} KB")
