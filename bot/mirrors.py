"""Автообновление списка казино из закрепа «Актуальные зеркала» в сером канале (канал ВИТУС).

Бот — админ канала, поэтому видит:
  • новые и отредактированные посты канала (если пост похож на «Актуальные зеркала» — берём его);
  • сообщение о закреплении поста;
  • закреп через getChat — проверяем раз в REFRESH_EVERY секунд.
Список хранится на листе «Настройки бота» и отдаётся мини-приложению через /api/mirrors.
"""
import asyncio
import html
import json
import logging
import re
import time

from aiogram import Bot
from aiogram.types import Message

from .sheets import SettingsStore

log = logging.getLogger(__name__)

KEY = "mirrors"
REFRESH_EVERY = 30 * 60
MARKER = "актуальные зеркала"

# Имя из поста → id в приложении (совпадает с логотипами и избранным)
ALIASES = {
    "joy": "joy", "joycasino": "joy", "vodka": "vodka", "vodkabet": "vodka", "vavada": "vavada", "stake": "stake",
    "honeymoney": "honey", "casinohype": "hype", "hype": "hype", "auf": "auf", "unlim": "unlim",
    "cryptoboss": "cboss", "kushcasino": "kush", "kush": "kush", "banda": "banda", "leebet": "leebet",
    "playfortuna": "fortuna", "jozz": "jozz", "booi": "booi", "panda": "panda", "faro": "faro",
    "apex": "apex", "eva": "eva", "fenix": "fenix", "beer": "beer",
}
LOGO = {"joy": "joycasino"}  # id → ключ логотипа, если отличается
CODE_RE = re.compile(r"^([A-Z0-9]{4,})\s*[—–-]+\s*(.+)$")
URL_RE = re.compile(r"https?://[^\s<>()]+")
TG_RE = re.compile(r"^https?://(t\.me|telegram\.me)/", re.I)


def message_text(message: Message) -> str:
    """Текст поста со ссылками: у скрытых ссылок (текст-ссылка) URL ставим после подписи."""
    if not (message.text or message.caption):
        return ""
    raw = message.html_text
    raw = re.sub(r'<a href="([^"]+)">(.*?)</a>', r"\2 \1", raw, flags=re.S)
    raw = re.sub(r"<[^>]+>", "", raw)
    return html.unescape(raw)


def is_mirrors_post(text: str) -> bool:
    low = text.lower()
    return MARKER in low and len(URL_RE.findall(text)) >= 3


def _slug(name: str) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", name.lower())


def _numbers(pattern: str, text: str) -> int:
    vals = [int(x) for x in re.findall(pattern, text, flags=re.I)]
    return max(vals) if vals else 0


def parse_mirrors(text: str) -> list[dict]:
    entries: list[dict] = []
    cur = None
    group = "main"
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "проверенн" in s.lower() and "времен" in s.lower():
            group = "proven"
            cur = None
            continue
        urls = URL_RE.findall(s)
        casino_urls = [u for u in urls if not TG_RE.match(u)]
        if casino_urls:
            url = casino_urls[0].rstrip(").,;")
            before = s[: s.find(casino_urls[0])]
            name = re.sub(r"[^\w\s.\-]", "", before).replace("_", " ").strip(" :.-")
            name = re.sub(r"\s+", " ", name)
            if not name:
                cur = None
                continue
            rest = s[s.find(casino_urls[0]) + len(casino_urls[0]):].strip(" .")
            cur = {"name": name, "url": url, "group": group, "desc": [rest] if rest else []}
            entries.append(cur)
        elif urls:  # строка только с t.me — служебная («все бонусы здесь»)
            cur = None
        elif cur is not None:
            cur["desc"].append(s)
    return [_finish(e) for e in entries]


def _finish(e: dict) -> dict:
    slug = _slug(e["name"])
    cid = ALIASES.get(slug, slug or "casino")
    codes, lines = [], []
    for d in e["desc"]:
        m = CODE_RE.match(d)
        if m:
            if m.group(1) != "VITUSSRAZOR":
                codes.append([m.group(1), m.group(2).strip()])
        else:
            lines.append(d)
    text = " ".join(lines).strip()
    full = " ".join(e["desc"])
    pct = _numbers(r"(\d{2,3})\s*%", full)
    fs = _numbers(r"(\d{2,5})\s*FS", full)
    if pct and fs:
        bonus = f"до {pct}% + {fs} FS"
    elif fs:
        bonus = f"до {fs} FS"
    elif pct:
        bonus = f"до {pct}%"
    else:
        bonus = (text.split(".")[0][:42]) if text else ""
    low = full.lower()
    tags = []
    if "без верифик" in low:
        tags.append("Без верификации")
    m = re.search(r"кешб[эе]к[^.\n]*?(\d{1,2})\s*%", low)
    if m:
        tags.append(f"Кешбэк до {m.group(1)}%")
    elif "кешб" in low:
        tags.append("Кешбэк")
    if "бездеп" in low:
        tags.append("Бездеп")
    if "без вагер" in low or "без вейджер" in low:
        tags.append("Без вейджера")
    if "розыгр" in low or "выиграй" in low:
        tags.append("Розыгрыш")
    proven = e["group"] == "proven" or "проверил" in low
    item = {"id": cid, "name": e["name"].upper(), "url": e["url"], "bonus": bonus, "text": text}
    if pct:
        item["pct"] = pct
    if fs:
        item["fs"] = fs
    if codes:
        item["codes"] = codes
    if tags:
        item["tags"] = tags
    if "без верифик" in low:
        item["noverif"] = True
    if proven:
        item["proven"] = True
    if e["group"] == "proven":
        item["group"] = "proven"
    if cid in LOGO:
        item["logo"] = LOGO[cid]
    return item


class Mirrors:
    def __init__(self, store: SettingsStore, chat_id: int, admin_ids: set[int]):
        self._store = store
        self.chat_id = chat_id
        self._admins = admin_ids
        self.items: list[dict] = []
        self.updated = 0
        self._last_text = ""

    async def load(self) -> None:
        try:
            raw = await self._store.get(KEY)
            if raw:
                data = json.loads(raw)
                self.items, self.updated = data.get("items", []), data.get("updated", 0)
                self._last_text = data.get("source", "")
        except Exception:
            log.exception("Не удалось загрузить зеркала")

    async def consider(self, message: Message, bot: Bot | None = None) -> bool:
        """Пост канала: если это «Актуальные зеркала» и он изменился — обновляем список."""
        text = message_text(message)
        if not is_mirrors_post(text) or text == self._last_text:
            return False
        items = parse_mirrors(text)
        if len(items) < 3:
            log.warning("Пост с зеркалами разобрать не удалось (казино: %s)", len(items))
            return False
        self.items, self.updated, self._last_text = items, int(time.time()), text
        try:
            await self._store.set(KEY, json.dumps(
                {"items": items, "updated": self.updated, "source": text}, ensure_ascii=False))
        except Exception:
            log.exception("Не удалось сохранить зеркала")
        log.info("Зеркала обновлены: %s казино", len(items))
        if bot:
            names = ", ".join(i["name"] for i in items)
            for admin_id in self._admins:
                try:
                    await bot.send_message(admin_id, f"🔄 Зеркала в приложении обновлены из закрепа: {len(items)} казино.\n\n{names}")
                except Exception:
                    pass
        return True

    async def refresh_from_pinned(self, bot: Bot) -> str:
        try:
            chat = await bot.get_chat(self.chat_id)
        except Exception as e:
            log.warning("Не удалось прочитать канал с зеркалами %s: %s", self.chat_id, e)
            return f"не удалось прочитать канал: {e}"
        pinned = chat.pinned_message
        if not pinned:
            return "в канале нет закреплённого поста"
        if not is_mirrors_post(message_text(pinned)):
            return "закреплён пост без «Актуальные зеркала»"
        changed = await self.consider(pinned, bot)
        return "обновлено" if changed else "без изменений"

    async def loop(self, bot: Bot) -> None:
        while True:
            result = await self.refresh_from_pinned(bot)
            log.info("Проверка закрепа с зеркалами: %s", result)
            await asyncio.sleep(REFRESH_EVERY)
