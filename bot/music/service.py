"""Музыкальная группа Виктора.

Виктор кидает в группу ссылку на YouTube → бот отвечает на его сообщение карточкой, которая живёт:
⏳ в очереди → ⬇️ скачиваю видео/звук (проценты) → ☁️ загружаю на Диск → 🎵 готово.
Готовая карточка: название, длительность, качество, кнопки «Папка / Видео / Звук / YouTube»,
отметка Виктора и Александра (публикатора) и кнопка «✅ Выложил в ВК» — после нажатия карточка
показывает, кто и когда выложил. Повторная ссылка не качается заново: бот отдаёт уже готовую папку.

Команды в группе (админы бота или группы):
  /musichere — включить бота в этой группе;   /musicoff — выключить;
  /publisher — ответом на сообщение Александра (или /publisher @username) — кого тегать для ВК;
  /todo — список треков, которые ещё не выложены в ВК (со ссылками на карточки).
Карточка: обложка, цветные кнопки, «🛠 Беру в работу» → «✅ Выложил в ВК» (Виктору приходит 🎉),
«🔊 Послушать здесь» — звук прямо в чат.
В личке админу: /gdrive — подключить Google Диск, /music — состояние.
"""
import asyncio
import hashlib
import hmac
import html
import itertools
import json
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiohttp import web

from . import gdrive, youtube

log = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))
KEY = "music"
TRACKS_KEY = "music_tracks"
TRACKS_LIMIT = 100
VID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|live/)([\w-]{11})")
EDIT_EVERY = 3.0
REGISTRY_SHEET = "Музыка"
REGISTRY_HEADER = ["Дата", "Прислал", "Название", "YouTube", "Длительность", "Папка", "Видео", "Звук", "ВК"]
GROUP_ADMIN = {"creator", "administrator"}


def _bar(frac: float) -> str:
    n = max(0, min(10, round(frac * 10)))
    return "▰" * n + "▱" * (10 - n) + f" {int(frac * 100)}%"


def _mention(user: dict | None) -> str:
    if not user:
        return ""
    if user.get("username"):
        return "@" + user["username"]
    return f'<a href="tg://user?id={user["id"]}">{html.escape(user.get("name") or "публикатор")}</a>'


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.0f} МБ" if n >= 1024 * 1024 else f"{n / 1024:.0f} КБ"


class Job:
    _ids = itertools.count(1)

    def __init__(self, url: str, chat_id: int, reply_to: int, sender: dict, title: str = ""):
        self.id = next(self._ids)
        self.url = url
        self.chat_id = chat_id
        self.reply_to = reply_to
        self.sender = sender
        self.title = title
        self.message_id = 0
        self.photo = False
        self.stage = "queue"
        self.frac = 0.0


class MusicService:
    def __init__(self, store, sheet, cfg):
        self._store = store
        self._sheet = sheet
        self.cfg = cfg
        self.admin_ids: set[int] = cfg.admin_ids
        self.chats: set[int] = set()
        self.publisher: dict | None = None
        self.token: dict = {}
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.active: dict[str, Job] = {}       # url → задача (чтобы одна ссылка не качалась дважды)
        self.failed: dict[int, Job] = {}
        self.tracks: dict[str, dict] = {}     # "chat:msg" → карточка трека (статус ВК и т.п.)
        self._drive: gdrive.Drive | None = None
        self._worker: asyncio.Task | None = None

    # ---------- настройки ----------
    async def load(self) -> None:
        if not self._store:
            return
        try:
            raw = await self._store.get(KEY)
            data = json.loads(raw) if raw else {}
        except Exception:
            log.exception("Не удалось загрузить настройки музыки")
            return
        self.chats = {int(c) for c in data.get("chats", [])}
        self.publisher = data.get("publisher")
        self.token = data.get("drive") or {}
        try:
            raw = await self._store.get(TRACKS_KEY)
            self.tracks = json.loads(raw) if raw else {}
        except Exception:
            log.exception("Не удалось загрузить карточки треков")

    async def save_tracks(self) -> None:
        while len(self.tracks) > TRACKS_LIMIT:
            self.tracks.pop(next(iter(self.tracks)))
        if self._store:
            try:
                await self._store.set(TRACKS_KEY, json.dumps(self.tracks, ensure_ascii=False, separators=(",", ":")))
            except Exception:
                log.exception("Не удалось сохранить карточки треков")

    async def save(self) -> None:
        if self._store:
            await self._store.set(KEY, json.dumps({"chats": sorted(self.chats), "publisher": self.publisher,
                                                   "drive": self.token}, ensure_ascii=False))

    @property
    def refresh_token(self) -> str:
        return self.cfg.google_drive_refresh_token or self.token.get("refresh_token", "")

    @property
    def oauth_ready(self) -> bool:
        return bool(self.cfg.google_oauth_client_id and self.cfg.google_oauth_client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{self.cfg.webapp_url}/oauth/google"

    def drive(self) -> gdrive.Drive:
        if not self.oauth_ready or not self.refresh_token:
            raise RuntimeError("Google Диск не подключён — админу: /gdrive в личке бота.")
        if self._drive is None:
            self._drive = gdrive.Drive(self.cfg.google_oauth_client_id, self.cfg.google_oauth_client_secret,
                                       self.refresh_token, self.cfg.music_drive_folder)
        return self._drive

    def _state(self, admin_id: int) -> str:
        sig = hmac.new(self.cfg.telegram_token.encode(), f"gdrive:{admin_id}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"{admin_id}.{sig}"

    def _check_state(self, state: str) -> int | None:
        try:
            admin_id = int(state.split(".")[0])
        except ValueError:
            return None
        return admin_id if admin_id in self.admin_ids and hmac.compare_digest(state, self._state(admin_id)) else None

    # ---------- реестр в Google-таблице ----------
    def _registry(self):
        import gspread
        book = self._sheet._spreadsheet()
        try:
            return book.worksheet(REGISTRY_SHEET)
        except gspread.WorksheetNotFound:
            ws = book.add_worksheet(REGISTRY_SHEET, rows=100, cols=len(REGISTRY_HEADER))
            ws.append_row(REGISTRY_HEADER)
            return ws

    async def _registry_add(self, row: list[str]) -> None:
        if not (self._sheet and self._sheet.enabled):
            return
        try:
            await asyncio.to_thread(lambda: self._registry().append_row(row, value_input_option="USER_ENTERED"))
        except Exception:
            log.exception("Не удалось записать трек в лист «Музыка»")

    async def _registry_vk(self, youtube_url: str, mark: str) -> None:
        if not (self._sheet and self._sheet.enabled):
            return

        def work():
            ws = self._registry()
            col = REGISTRY_HEADER.index("YouTube") + 1
            for i, value in enumerate(ws.col_values(col), start=1):
                if value == youtube_url:
                    ws.update_cell(i, REGISTRY_HEADER.index("ВК") + 1, mark)
        try:
            await asyncio.to_thread(work)
        except Exception:
            log.exception("Не удалось отметить ВК в листе «Музыка»")

    # ---------- очередь ----------
    def start(self, bot: Bot) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._loop(bot))

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()

    async def _loop(self, bot: Bot) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self._process(bot, job)
            except Exception:
                log.exception("Музыка: задача %s упала", job.url)
            finally:
                self.active.pop(job.url, None)
                self.queue.task_done()

    async def enqueue(self, bot: Bot, message: Message, url: str) -> None:
        if url in self.active:
            return
        sender = {"id": message.from_user.id, "name": message.from_user.full_name,
                  "username": message.from_user.username or ""}
        job = Job(url, message.chat.id, message.message_id, sender)
        ahead = len(self.active)  # уже в работе и в очереди
        self.active[url] = job
        text = "⏳ Ссылка принята" + (f", в очереди: {ahead}" if ahead else ", начинаю") + f"\n{html.escape(url)}"
        await self._post(bot, job, text)
        await self.queue.put(job)

    async def _post(self, bot: Bot, job: Job, text: str) -> None:
        """Первое сообщение карточки: обложка YouTube + подпись (или просто текст, если обложки нет)."""
        m = VID_RE.search(job.url)
        if m:
            try:
                sent = await bot.send_photo(job.chat_id, f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg",
                                            caption=text, parse_mode="HTML", reply_to_message_id=job.reply_to,
                                            allow_sending_without_reply=True)
                job.message_id, job.photo = sent.message_id, True
                return
            except Exception as e:
                log.info("Обложка не отправилась (%s) — карточка будет текстом", e)
        sent = await bot.send_message(job.chat_id, text, parse_mode="HTML", reply_to_message_id=job.reply_to,
                                      disable_web_page_preview=True, allow_sending_without_reply=True)
        job.message_id, job.photo = sent.message_id, False

    def _status_text(self, job: Job) -> str:
        title = f"🎵 <b>{html.escape(job.title)}</b>" if job.title else f"🎵 {html.escape(job.url)}"
        stage = {
            "info": "🔎 Смотрю видео…",
            "video": f"⬇️ Видео {youtube.MAX_HEIGHT}p  {_bar(job.frac)}",
            "audio": f"⬇️ Звук  {_bar(job.frac)}",
            "check": "🔎 Проверяю Диск…",
            "up_video": f"☁️ Загружаю видео на Диск  {_bar(job.frac)}",
            "up_audio": f"☁️ Загружаю звук на Диск  {_bar(job.frac)}",
            "up_cover": "☁️ Обложка…",
        }.get(job.stage, "⏳ Начинаю…")
        return f"{title}\n{stage}"

    async def _ticker(self, bot: Bot, job: Job) -> None:
        last = ""
        while True:
            text = self._status_text(job)
            if text != last:
                try:
                    await self._raw_edit(bot, job.chat_id, job.message_id, job.photo, text)
                    last = text
                except Exception as e:
                    if "retry after" in str(e).lower():
                        await asyncio.sleep(10)
            await asyncio.sleep(EDIT_EVERY)

    @staticmethod
    async def _halt(task: asyncio.Task) -> None:
        """Остановить обновление прогресса и дождаться, чтобы оно не перезаписало готовую карточку."""
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    def _set(self, job: Job, stage: str, frac: float = 0.0) -> None:
        job.stage, job.frac = stage, frac

    async def _process(self, bot: Bot, job: Job) -> None:
        ticker = asyncio.create_task(self._ticker(bot, job))
        workdir = Path(tempfile.mkdtemp(prefix="music_"))
        try:
            self._set(job, "info")
            drive = self.drive()
            items = await asyncio.to_thread(youtube.expand, job.url)
            if not items:
                raise RuntimeError("По ссылке нет видео.")
            if len(items) > 1:  # плейлист: каждый трек — отдельная карточка
                await self._halt(ticker)
                await self._edit(bot, job, f"📃 Плейлист: {len(items)} видео — ставлю каждое в очередь 👇")
                for it in items:
                    if it["url"] in self.active:
                        continue
                    sub = Job(it["url"], job.chat_id, job.message_id, job.sender, it["title"])
                    self.active[sub.url] = sub
                    sub.reply_to = job.reply_to
                    await self._post(bot, sub, f"⏳ В очереди: {html.escape(sub.title or sub.url)}")
                    await self.queue.put(sub)
                return
            video_id = items[0]["id"]
            job.title = items[0]["title"] or job.title

            self._set(job, "check")
            existing = await asyncio.to_thread(drive.find_track, video_id)
            if existing:
                existing["vid"] = video_id
                await self._halt(ticker)
                await self._card(bot, job, None, existing, again=True)
                return

            def on_info(tr):
                job.title = tr.nice_title

            track = await asyncio.to_thread(youtube.download, items[0]["url"], workdir,
                                            lambda st, f: self._set(job, st, f), on_info)
            when = datetime.now(MSK)
            folder = await asyncio.to_thread(drive.track_folder, track.safe_name, track.video_id, when)
            desc = f"{track.nice_title}\n{track.url}\nПрислал: {job.sender.get('name')}"
            files = []
            for stage, path in (("up_video", track.video_path), ("up_audio", track.audio_path), ("up_cover", track.cover_path)):
                if not path:
                    continue
                self._set(job, stage)
                fid = await asyncio.to_thread(drive.upload, path, folder, lambda f, s=stage: self._set(job, s, f), desc)
                files.append({"id": fid, "name": path.name, "size": str(path.stat().st_size)})
            await self._halt(ticker)
            await self._card(bot, job, track, {"folder": folder, "name": track.safe_name, "files": files})
            links = {f["name"].rsplit(".", 1)[-1]: gdrive.file_url(f["id"]) for f in files}
            await self._registry_add([
                when.strftime("%d.%m.%Y %H:%M"), job.sender.get("name", ""), track.nice_title, track.url,
                track.duration_str, gdrive.folder_url(folder), links.get("mp4", ""),
                next((v for k, v in links.items() if k in {"m4a", "opus", "webm", "mp3"}), ""), "",
            ])
        except Exception as e:
            await self._halt(ticker)
            log.exception("Музыка: не удалось обработать %s", job.url)
            reason = youtube.explain(e)
            self.failed[job.id] = job
            while len(self.failed) > 50:
                self.failed.pop(next(iter(self.failed)))
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔁 Попробовать снова",
                                                                              callback_data=f"mr:{job.id}")]])
            title = html.escape(job.title or job.url)
            await self._edit(bot, job, f"⚠️ Не получилось: {title}\n{html.escape(reason)}", kb)
            if "YOUTUBE_COOKIES" in reason or "Диск" in reason:
                for admin_id in self.admin_ids:
                    try:
                        await bot.send_message(admin_id, f"🎵 Музыкальная группа: {html.escape(reason)}", parse_mode="HTML")
                    except Exception:
                        pass
        finally:
            ticker.cancel()
            shutil.rmtree(workdir, ignore_errors=True)

    @staticmethod
    async def _raw_edit(bot: Bot, chat_id: int, message_id: int, photo: bool, text: str, kb=None) -> None:
        if photo:
            await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text,
                                           parse_mode="HTML", reply_markup=kb)
        else:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML",
                                        disable_web_page_preview=True, reply_markup=kb)

    async def _edit(self, bot: Bot, job: Job, text: str, kb=None) -> None:
        try:
            await self._raw_edit(bot, job.chat_id, job.message_id, job.photo, text, kb)
        except Exception as e:
            if "not modified" in str(e):
                return
            sent = await bot.send_message(job.chat_id, text, parse_mode="HTML", reply_markup=kb,
                                          reply_to_message_id=job.reply_to, allow_sending_without_reply=True,
                                          disable_web_page_preview=True)
            job.message_id, job.photo = sent.message_id, False

    async def _card(self, bot: Bot, job: Job, track, saved: dict, again: bool = False) -> None:
        files = saved["files"]
        video = next((f for f in files if f["name"].endswith(".mp4")), None)
        audio = next((f for f in files if f["name"].rsplit(".", 1)[-1] in {"m4a", "opus", "webm", "mp3"}), None)
        info = ""
        if track:
            q = [f"⏱ {track.duration_str}"]
            if video:
                q.append(f"🎬 {track.height or youtube.MAX_HEIGHT}p · {_size(int(video['size']))}")
            if audio:
                codec = {"mp4a": "AAC", "opus": "Opus"}.get(track.audio_codec, track.audio_codec.upper() or "звук")
                q.append(f"🎧 {codec} {track.audio_kbps} kbps" if track.audio_kbps else f"🎧 {codec}")
            info = " · ".join(q)
        old = next((r for r in self.tracks.values() if r.get("vid") and r["vid"] == (track.video_id if track else saved.get("vid"))
                    and r.get("vk") == "done"), None) if again else None
        rec = {
            "t": track.nice_title if track else saved.get("name") or job.title,
            "u": track.url if track else job.url, "vid": track.video_id if track else saved.get("vid", ""),
            "i": info, "again": again, "s": job.sender, "f": saved["folder"],
            "v": video["id"] if video else "", "a": audio["id"] if audio else "",
            "an": audio["name"] if audio else "", "p": job.photo, "r": job.reply_to,
            "vk": "done" if old else "wait", "by": old.get("by", "") if old else "", "at": old.get("at", "") if old else "",
            "c": int(time.time()),
        }
        key = f"{job.chat_id}:{job.message_id}"
        self.tracks[key] = rec
        text, kb = self.render(rec)
        await self._edit(bot, job, text, kb)
        new_key = f"{job.chat_id}:{job.message_id}"  # карточка могла переехать в новое сообщение
        if new_key != key:
            self.tracks[new_key] = self.tracks.pop(key)
            self.tracks[new_key]["p"] = job.photo
        await self.save_tracks()

    def render(self, rec: dict) -> tuple[str, InlineKeyboardMarkup]:
        lines = [f"🎵 <b>{html.escape(rec['t'])}</b>"]
        if rec.get("i"):
            lines.append(rec["i"])
        vk = rec.get("vk", "wait")
        vk_icon = {"wait": "⏳ ВК", "work": "🛠 ВК", "done": "✅ ВК"}[vk]
        lines.append(f"\n✅ Скачано  ·  ✅ На Диске  ·  {vk_icon}" + ("  ·  ♻️ уже было" if rec.get("again") else ""))
        lines.append("")
        lines.append(f"👤 Прислал: {_mention(rec.get('s'))}")
        pub = _mention(self.publisher) if self.publisher else ""
        if vk == "wait":
            lines.append(f"📤 {pub}, выложи в ВК в плейлист 👇" if pub else "📤 Публикатор не назначен — /publisher")
        elif vk == "work":
            lines.append(f"🛠 {html.escape(rec.get('by', ''))} выкладывает в ВК · с {rec.get('at', '')}")
        else:
            lines.append(f"✅ В ВК выложил {html.escape(rec.get('by', ''))} · {rec.get('at', '')}")

        B = InlineKeyboardButton
        rows = [[B(text="📁 Папка на Диске", url=gdrive.folder_url(rec["f"]), style="primary")]]
        pair = []
        if rec.get("v"):
            pair.append(B(text="🎬 Видео 1080p", url=gdrive.file_url(rec["v"])))
        if rec.get("a"):
            pair.append(B(text="🎧 Звук", url=gdrive.file_url(rec["a"])))
        if pair:
            rows.append(pair)
        row = [B(text="▶️ YouTube", url=rec["u"])]
        if rec.get("a"):
            row.insert(0, B(text="🔊 Послушать здесь", callback_data="ml"))
        rows.append(row)
        if vk == "wait":
            rows.append([B(text="🛠 Беру в работу", callback_data="mt", style="primary"),
                         B(text="✅ Выложил в ВК", callback_data="mv", style="success")])
        elif vk == "work":
            rows.append([B(text="✅ Выложил в ВК", callback_data="mv", style="success"),
                         B(text="↩️ Отмена", callback_data="mu")])
        else:
            rows.append([B(text="↩️ Снять отметку ВК", callback_data="mu", style="danger")])
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)

    def pending(self, chat_id: int) -> list[tuple[str, dict]]:
        """Не выложенные треки группы; один трек — одна строка (самая свежая карточка)."""
        latest: dict[str, tuple[str, dict]] = {}
        for k, r in self.tracks.items():
            if k.startswith(f"{chat_id}:"):
                latest[r.get("vid") or k] = (k, r)
        return [(k, r) for k, r in latest.values() if r.get("vk") != "done"]

    def listen_file(self, rec: dict, workdir: Path) -> Path:
        path = workdir / (rec.get("an") or "track.m4a")
        self.drive().download(rec["a"], path)
        return path

    # ---------- проверки ----------
    async def can_manage(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        if user_id in self.admin_ids:
            return True
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return member.status in GROUP_ADMIN
        except Exception:
            return False

    def status_text(self, chat_titles=None) -> str:
        drive = f"✅ подключён ({self.token.get('email') or 'аккаунт Google'})" if self.refresh_token else "❌ не подключён — /gdrive"
        if not self.oauth_ready:
            drive = "❌ нет GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET в Railway"
        groups = ", ".join((chat_titles or {}).get(c, str(c)) for c in self.chats) or "нет — /musichere в группе"
        cookies = "✅ заданы" if os.getenv("YOUTUBE_COOKIES") else "— не заданы"
        proxy = "✅ задан" if os.getenv("YOUTUBE_PROXY") else "— не задан"
        return (f"🎵 <b>Музыка</b>\n\n☁️ Google Диск: {drive}\n📁 Папка: «{html.escape(self.cfg.music_drive_folder)}»\n"
                f"👥 Группы: {html.escape(groups)}\n📤 Публикатор ВК: {_mention(self.publisher) or 'не назначен'}\n"
                f"🍪 YouTube cookies: {cookies}\n🌐 Прокси: {proxy}\n⏳ В работе: {len(self.active)}")


def setup_music_router(music: MusicService, chats=None) -> Router:
    router = Router()
    in_group = F.chat.type.in_({"group", "supergroup"})

    @router.message(in_group, Command("musichere"))
    async def music_here(message: Message, bot: Bot):
        if not await music.can_manage(bot, message.chat.id, message.from_user.id):
            return
        music.chats.add(message.chat.id)
        await music.save()
        me = await bot.get_chat_member(message.chat.id, bot.id)
        warn = "" if me.status in GROUP_ADMIN else (
            "\n\n⚠️ Сделайте меня администратором группы (права можно все выключить) — иначе я не вижу ссылки.")
        drive = "" if music.refresh_token else "\n☁️ Google Диск ещё не подключён — админу: /gdrive в личке бота."
        await message.reply("🎵 Готово! Кидайте сюда ссылки на YouTube — я скачаю видео в 1080p и звук отдельно, "
                            "залью на Google Диск и пришлю ссылки.\n/todo — что ещё не выложено в ВК." + warn + drive)

    @router.message(in_group, Command("musicoff"))
    async def music_off(message: Message, bot: Bot):
        if not await music.can_manage(bot, message.chat.id, message.from_user.id):
            return
        music.chats.discard(message.chat.id)
        await music.save()
        await message.reply("🔕 Больше не обрабатываю ссылки в этой группе. Включить снова: /musichere")

    @router.message(in_group, Command("publisher"))
    async def set_publisher(message: Message, bot: Bot):
        if not await music.can_manage(bot, message.chat.id, message.from_user.id):
            return
        target = message.reply_to_message.from_user if message.reply_to_message else None
        arg = (message.text or "").split(maxsplit=1)[1:] or [""]
        if target and not target.is_bot:
            music.publisher = {"id": target.id, "name": target.full_name, "username": target.username or ""}
        elif arg[0].startswith("@"):
            music.publisher = {"id": 0, "name": arg[0][1:], "username": arg[0][1:]}
        else:
            await message.reply("Ответь командой /publisher на любое сообщение Александра или напиши /publisher @username")
            return
        await music.save()
        await message.reply(f"📤 Теперь для ВК тегаю {_mention(music.publisher)}", parse_mode="HTML")

    def has_links(message: Message) -> bool:
        return message.chat.id in music.chats and bool(youtube.find_links(message.text or message.caption or ""))

    @router.message(in_group, has_links)
    async def on_links(message: Message, bot: Bot):
        if chats:
            await chats.note(message.chat)
        for url in youtube.find_links(message.text or message.caption or ""):
            await music.enqueue(bot, message, url)

    async def may_publish(cb: CallbackQuery, bot: Bot) -> bool:
        user, pub = cb.from_user, music.publisher or {}
        return bool(user.id in music.admin_ids or user.id == pub.get("id")
                    or (pub.get("username") and (user.username or "").lower() == pub["username"].lower())
                    or await music.can_manage(bot, cb.message.chat.id, user.id))

    @router.callback_query(F.data.in_({"mt", "mv", "mu"}))
    async def vk_status(cb: CallbackQuery, bot: Bot):
        if not await may_publish(cb, bot):
            await cb.answer("Это кнопка публикатора 🙂", show_alert=True)
            return
        key = f"{cb.message.chat.id}:{cb.message.message_id}"
        rec = music.tracks.get(key)
        if not rec:
            await cb.answer("Карточка старая — пришлите ссылку ещё раз", show_alert=True)
            return
        user = cb.from_user
        when = datetime.now(MSK).strftime("%d.%m %H:%M")
        prev = rec.get("vk")
        rec["vk"] = {"mt": "work", "mv": "done", "mu": "wait"}[cb.data]
        rec["by"], rec["at"] = (user.full_name, when) if rec["vk"] != "wait" else ("", "")
        text, kb = music.render(rec)
        try:
            await music._raw_edit(bot, cb.message.chat.id, cb.message.message_id, bool(cb.message.photo), text, kb)
        except Exception as e:
            if "not modified" not in str(e):
                raise
        for other in music.tracks.values():  # другие карточки того же трека (ссылку присылали повторно)
            if other is not rec and rec.get("vid") and other.get("vid") == rec["vid"]:
                other.update(vk=rec["vk"], by=rec["by"], at=rec["at"])
        await music.save_tracks()
        await cb.answer({"work": "Взято в работу 🛠", "done": "Отмечено 🎉", "wait": "Отметка снята"}[rec["vk"]])
        if rec["vk"] == "done" and prev != "done":
            sender = _mention(rec.get("s"))
            await bot.send_message(cb.message.chat.id, f"🎉 {sender}, «{html.escape(rec['t'])}» уже в ВК! "
                                   f"Спасибо, {html.escape(user.first_name)} 🙌", parse_mode="HTML",
                                   reply_to_message_id=cb.message.message_id, allow_sending_without_reply=True)
        await music._registry_vk(rec["u"], f"✅ {user.full_name}, {when}" if rec["vk"] == "done"
                                 else ("🛠 " + user.full_name if rec["vk"] == "work" else ""))

    @router.callback_query(F.data == "ml")
    async def listen(cb: CallbackQuery, bot: Bot):
        rec = music.tracks.get(f"{cb.message.chat.id}:{cb.message.message_id}")
        if not rec or not rec.get("a"):
            await cb.answer("Звук не найден — откройте кнопкой «🎧 Звук»", show_alert=True)
            return
        if rec.get("tg"):
            await cb.answer()
            await bot.send_audio(cb.message.chat.id, rec["tg"], reply_to_message_id=cb.message.message_id,
                                 allow_sending_without_reply=True)
            return
        await cb.answer("Секунду, достаю звук с Диска… 🎧")
        workdir = Path(tempfile.mkdtemp(prefix="listen_"))
        try:
            path = await asyncio.to_thread(music.listen_file, rec, workdir)
            artist, _, name = rec["t"].partition(" — ")
            sent = await bot.send_audio(cb.message.chat.id, FSInputFile(path), title=name or rec["t"],
                                        performer=artist if name else None,
                                        reply_to_message_id=cb.message.message_id, allow_sending_without_reply=True)
            if sent.audio:
                rec["tg"] = sent.audio.file_id
                await music.save_tracks()
        except Exception as e:
            log.exception("Музыка: не удалось отправить звук")
            await bot.send_message(cb.message.chat.id, f"⚠️ Не получилось отправить звук: {html.escape(str(e))[:200]}",
                                   reply_to_message_id=cb.message.message_id, allow_sending_without_reply=True)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    @router.message(in_group, Command("todo"))
    async def todo(message: Message):
        if message.chat.id not in music.chats:
            return
        items = music.pending(message.chat.id)
        if not items:
            await message.reply("🎉 Всё выложено в ВК — хвостов нет!")
            return
        internal = str(message.chat.id).removeprefix("-100")
        lines = [f"📋 <b>Ждут публикации в ВК: {len(items)}</b>\n"]
        now = time.time()
        for i, (key, r) in enumerate(items, 1):
            link = f"https://t.me/c/{internal}/{key.split(':')[1]}"
            days = int((now - r.get("c", now)) // 86400)
            age = "сегодня" if days == 0 else f"{days} дн."
            state = "🛠 " + html.escape(r.get("by", "")) if r.get("vk") == "work" else "⏳"
            lines.append(f"{i}. <a href=\"{link}\">{html.escape(r['t'])}</a> — {state} · {age}")
        pub = _mention(music.publisher)
        if pub:
            lines.append(f"\n{pub}, это твой список 👆")
        await message.reply("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

    @router.callback_query(F.data.startswith("mr:"))
    async def retry(cb: CallbackQuery, bot: Bot):
        job = music.failed.pop(int(cb.data.split(":")[1]), None)
        if not job:
            await cb.answer("Пришлите ссылку ещё раз", show_alert=True)
            return
        if job.url in music.active:
            await cb.answer("Уже в работе")
            return
        music.active[job.url] = job
        job.stage = "queue"
        await cb.message.edit_text(f"⏳ Пробую снова\n{html.escape(job.url)}", disable_web_page_preview=True)
        await music.queue.put(job)
        await cb.answer()

    # ---------- личка админа ----------
    is_admin = (F.chat.type == "private") & F.from_user.id.func(lambda uid: uid in music.admin_ids)

    @router.message(is_admin, Command("gdrive"))
    async def gdrive_cmd(message: Message):
        if not music.oauth_ready:
            await message.answer("Сначала добавьте в Railway переменные GOOGLE_OAUTH_CLIENT_ID и "
                                 "GOOGLE_OAUTH_CLIENT_SECRET (инструкция в README, раздел «Музыка»).")
            return
        if not music.cfg.webapp_url:
            await message.answer("Нужен WEBAPP_URL — на него Google вернёт после входа.")
            return
        link = gdrive.auth_link(music.cfg.google_oauth_client_id, music.redirect_uri, music._state(message.from_user.id))
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔐 Войти через Google", url=link)]])
        await message.answer("Войди в аккаунт Google, на Диск которого складывать музыку, и разреши доступ.\n"
                             "Бот увидит только файлы, которые создаст сам.", reply_markup=kb)

    @router.message(is_admin, Command("music"))
    async def music_status(message: Message):
        titles = {cid: info["title"] for cid, info in (chats.chats if chats else {}).items()}
        await message.answer(music.status_text(titles), parse_mode="HTML")

    return router


def oauth_handler(music: MusicService, bot: Bot):
    async def handle(request: web.Request):
        def page(title: str, text: str, status: int = 200):
            body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                    f"<body style='font-family:system-ui;background:#0b0b0c;color:#eee;display:grid;place-items:center;"
                    f"min-height:90vh;text-align:center'><div><h2>{title}</h2><p>{text}</p></div>")
            return web.Response(text=body, content_type="text/html", status=status)

        admin_id = music._check_state(request.query.get("state", ""))
        if not admin_id:
            return page("Ссылка устарела", "Запросите новую командой /gdrive в боте.", 400)
        if request.query.get("error") or not request.query.get("code"):
            return page("Вход отменён", "Можно попробовать ещё раз: /gdrive в боте.", 400)
        try:
            data = await gdrive.exchange_code(music.cfg.google_oauth_client_id, music.cfg.google_oauth_client_secret,
                                              music.redirect_uri, request.query["code"])
        except Exception as e:
            log.exception("Google OAuth")
            return page("Не получилось", html.escape(str(e)), 400)
        music.token = data
        music._drive = None
        try:
            await music.save()
            folder = await asyncio.to_thread(lambda: music.drive().root())
            text = (f"✅ Google Диск подключён: {data.get('email') or 'аккаунт'}\n"
                    f"Папка для музыки: {gdrive.folder_url(folder)}")
        except Exception as e:
            log.exception("Google Drive после входа")
            text = f"⚠️ Вход прошёл, но Диск ответил ошибкой: {e}"
        try:
            await bot.send_message(admin_id, text, disable_web_page_preview=True)
        except Exception:
            pass
        return page("Готово ✅", "Google Диск подключён. Можно закрыть страницу и вернуться в Telegram.")

    return handle


PRIVACY_HTML = """<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>
<title>Политика конфиденциальности</title>
<body style='font-family:system-ui;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;background:#0b0b0c;color:#eee'>
<h1>Политика конфиденциальности</h1>
<p>Этот Telegram-бот сохраняет музыкальные видео, ссылки на которые участники присылают в рабочую группу,
в Google Диск владельца бота.</p>
<h3>Какие данные Google используются</h3>
<p>Бот запрашивает только доступ <b>drive.file</b>: он видит и изменяет исключительно файлы и папки,
которые создал сам. Остальное содержимое Диска боту недоступно. Также бот получает адрес почты аккаунта,
чтобы показать администратору, какой Диск подключён.</p>
<h3>Хранение и передача</h3>
<p>Токен доступа хранится в закрытых настройках бота и используется только для загрузки файлов.
Данные не продаются и не передаются третьим лицам.</p>
<h3>Отзыв доступа</h3>
<p>Доступ можно отозвать в любой момент: <a style='color:#d4b26a' href='https://myaccount.google.com/permissions'>myaccount.google.com/permissions</a>.</p>
</body>"""


async def privacy_handler(_request):
    return web.Response(text=PRIVACY_HTML, content_type="text/html")
