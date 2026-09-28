"""Личный Телеграм-бот Джарвиса: пишите или наговаривайте голосовые с телефона — Джарвис на компьютере выполняет.

Работает без сервера: компьютер сам опрашивает Telegram (long polling). Отвечает только хозяйке —
её Telegram ID запоминается при первой команде /start с кодом привязки (код виден в окне Джарвиса).
"""
import secrets
import tempfile
import threading
import time
from pathlib import Path

import requests

from . import config, storage

API = "https://api.telegram.org"
STATE = {"ok": None, "note": "не настроен", "username": ""}
KEYBOARD = {"keyboard": [[{"text": "📋 Дела"}, {"text": "🗂 В работе"}, {"text": "📬 Почта"}],
                         [{"text": "☀️ Сводка дня"}, {"text": "💻 Компьютер"}, {"text": "📸 Скриншот"}]],
            "resize_keyboard": True, "is_persistent": True}
BUTTONS = {
    "📋 Дела": "Какие у меня личные дела и напоминания?",
    "🗂 В работе": "Что у меня в работе в Notion?",
    "📬 Почта": "Проверь почту и перескажи главное",
    "☀️ Сводка дня": "Сводка дня: дела, проекты, почта, погода",
    "💻 Компьютер": "Как там компьютер? Загрузка, память, батарея",
}
PAIR_CODE = f"{secrets.randbelow(900000) + 100000}"


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def _call(method: str, **params):
    files = params.pop("files", None)
    r = requests.post(f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/{method}", data=params if files else None,
                      json=None if files else params, files=files, timeout=params.get("timeout", 20) + 15)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram ответил ошибкой"))
    return data["result"]


def owner() -> int | None:
    v = str(config.TELEGRAM_OWNER_ID or "").strip()
    return int(v) if v.lstrip("-").isdigit() else None


# ---------- Отправка (используется и инструментами Джарвиса) ----------

def send(text: str, buttons: list | None = None, chat_id: int | None = None) -> bool:
    chat = chat_id or owner()
    if not (enabled() and chat):
        return False
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]:
        params = {"chat_id": chat, "text": chunk}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        _call("sendMessage", **params)
    return True


def send_file(path: str, caption: str = "", chat_id: int | None = None) -> bool:
    chat = chat_id or owner()
    if not (enabled() and chat):
        return False
    p = Path(path)
    method, field = ("sendPhoto", "photo") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else ("sendDocument", "document")
    with p.open("rb") as f:
        _call(method, chat_id=chat, caption=caption[:1000], files={field: (p.name, f)})
    return True


def send_voice(text: str, chat_id: int) -> bool:
    """Ответ голосом (OGG/Opus — как обычное голосовое в Телеграме)."""
    import os
    if not os.getenv("OPENAI_API_KEY"):
        return False
    import openai
    fd, path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        from .speech import for_speech
        params = dict(model="gpt-4o-mini-tts", voice=config.OPENAI_VOICE, input=for_speech(text)[:3500], response_format="opus",
                      instructions=config.VOICE_STYLE, speed=config.VOICE_SPEED)
        try:
            with openai.OpenAI().audio.speech.with_streaming_response.create(**params) as r:
                r.stream_to_file(path)
        except openai.BadRequestError:
            params.pop("speed")
            with openai.OpenAI().audio.speech.with_streaming_response.create(**params) as r:
                r.stream_to_file(path)
        with open(path, "rb") as f:
            _call("sendVoice", chat_id=chat_id, files={"voice": ("jarvis.ogg", f)})
        return True
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------- Приём ----------

class Bot:
    def __init__(self, ask, confirmer=None):
        self.ask = ask
        self.confirmer = confirmer
        self.offset = 0
        self.confirm_msgs: dict[str, tuple[int, int]] = {}  # id подтверждения → (chat, message_id)

    def start(self):
        if not enabled():
            return
        try:
            me = _call("getMe")
            STATE.update(ok=True, username=me["username"],
                         note=f"@{me['username']}" + ("" if owner() else " · ждёт привязки"))
        except Exception as e:  # noqa: BLE001
            STATE.update(ok=False, note=f"ошибка: {e}"[:120])
            print(f"⚠ Телеграм: {e}")
            return
        if not owner():
            print(f"📱 Телеграм: откройте @{STATE['username']} и отправьте:  /start {PAIR_CODE}")
        if self.confirmer:
            self.confirmer.notifiers.append(self._confirm_request)
            self.confirmer.resolvers.append(self._confirm_resolved)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                updates = _call("getUpdates", offset=self.offset, timeout=30,
                                allowed_updates=["message", "callback_query"])
                for u in updates:
                    self.offset = u["update_id"] + 1
                    threading.Thread(target=self._handle, args=(u,), daemon=True).start()
            except requests.RequestException:
                time.sleep(5)
            except Exception as e:  # noqa: BLE001
                print(f"⚠ Телеграм: {e}")
                time.sleep(5)

    def _handle(self, u: dict):
        if "callback_query" in u:
            return self._on_button(u["callback_query"])
        msg = u.get("message") or {}
        chat, user = msg.get("chat", {}).get("id"), msg.get("from", {}).get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not chat:
            return
        # привязка хозяйки
        if not owner():
            if text.startswith("/start") and PAIR_CODE in text:
                self._save_owner(user)
                _call("sendMessage", chat_id=chat, reply_markup=KEYBOARD,
                      text=f"Моё почтение, {config.USER_NAME}. Телеграм привязан — я к вашим услугам и здесь.\n\n"
                           "Пишите или наговаривайте голосовые. Кнопки внизу — быстрые команды.")
            else:
                _call("sendMessage", chat_id=chat, text="Отправьте /start и код привязки из окна Джарвиса.")
            return
        if user != owner():
            return  # чужим не отвечаем вовсе
        if text in ("/start", "/help"):
            _call("sendMessage", chat_id=chat, reply_markup=KEYBOARD,
                  text="К вашим услугам. Пишите задачу текстом или голосовым.\n"
                       "/screen — скриншот экрана, /tasks — дела, /notion — проекты в работе, /mail — почта.")
            return
        if text in ("📸 Скриншот", "/screen"):
            from .tools.system import screenshot
            path = screenshot().split(": ", 1)[-1]
            send_file(path, "Ваш экран", chat)
            return
        commands = {"/tasks": "📋 Дела", "/notion": "🗂 В работе", "/mail": "📬 Почта"}
        text = BUTTONS.get(commands.get(text, text), text)

        voice_in = msg.get("voice") or msg.get("audio")
        if voice_in:
            text = self._transcribe(voice_in["file_id"])
            if not text:
                _call("sendMessage", chat_id=chat, text="Не разобрал голосовое, повторите, пожалуйста.")
                return
            _call("sendMessage", chat_id=chat, text=f"🎙 «{text}»")
        for key in ("document", "photo"):
            if msg.get(key):
                item = msg[key][-1] if key == "photo" else msg[key]
                saved = self._download(item["file_id"], msg.get("document", {}).get("file_name") or f"photo_{int(time.time())}.jpg")
                text = f"{text}\n[Прислан файл, сохранён: {saved}]".strip()
        if not text:
            return

        typing = threading.Event()
        threading.Thread(target=self._typing, args=(chat, typing), daemon=True).start()
        try:
            answer = self.ask(f"[Сообщение из Телеграма] {text}")
        finally:
            typing.set()
        send(answer, chat_id=chat)
        if voice_in:
            try:
                send_voice(answer, chat)
            except Exception:  # noqa: BLE001
                pass

    def _typing(self, chat: int, stop: threading.Event):
        while not stop.is_set():
            try:
                _call("sendChatAction", chat_id=chat, action="typing")
            except Exception:  # noqa: BLE001
                pass
            stop.wait(4)

    def _file_url(self, file_id: str) -> tuple[str, str]:
        f = _call("getFile", file_id=file_id)
        return f"{API}/file/bot{config.TELEGRAM_BOT_TOKEN}/{f['file_path']}", f["file_path"]

    def _transcribe(self, file_id: str) -> str:
        import os
        if not os.getenv("OPENAI_API_KEY"):
            return ""
        import openai
        url, fp = self._file_url(file_id)
        data = requests.get(url, timeout=60).content
        suffix = Path(fp).suffix or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
        try:
            with open(tmp.name, "rb") as f:
                return openai.OpenAI().audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe", file=f, language="ru").text.strip()
        finally:
            os.remove(tmp.name)

    def _download(self, file_id: str, name: str) -> str:
        url, _ = self._file_url(file_id)
        folder = Path.home() / "Downloads" / "Jarvis"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / Path(name).name
        path.write_bytes(requests.get(url, timeout=120).content)
        return str(path)

    def _save_owner(self, user_id: int):
        from .dashboard import _write_env
        _write_env({"TELEGRAM_OWNER_ID": str(user_id)})
        config.TELEGRAM_OWNER_ID = str(user_id)
        STATE.update(note=f"@{STATE['username']} · привязан")
        storage.log("jarvis", "Телеграм привязан")

    # ---- подтверждения кнопками
    def _confirm_request(self, cid: str, question: str):
        if not owner():
            return
        m = _call("sendMessage", chat_id=owner(), text=f"⚠️ Джарвис просит разрешения:\n\n{question}",
                  reply_markup={"inline_keyboard": [[{"text": "✅ Да", "callback_data": f"ok:{cid}"},
                                                     {"text": "❌ Нет", "callback_data": f"no:{cid}"}]]})
        self.confirm_msgs[cid] = (owner(), m["message_id"])

    def _confirm_resolved(self, cid: str, yes: bool):
        chat_msg = self.confirm_msgs.pop(cid, None)
        if chat_msg:
            try:
                _call("editMessageReplyMarkup", chat_id=chat_msg[0], message_id=chat_msg[1],
                      reply_markup={"inline_keyboard": [[{"text": "✅ Разрешено" if yes else "❌ Отменено",
                                                          "callback_data": "done"}]]})
            except Exception:  # noqa: BLE001
                pass

    def _on_button(self, q: dict):
        if q.get("from", {}).get("id") != owner():
            return
        data = q.get("data", "")
        if ":" in data and self.confirmer:
            kind, cid = data.split(":", 1)
            self.confirmer.answer(cid, kind == "ok")
        try:
            _call("answerCallbackQuery", callback_query_id=q["id"])
        except Exception:  # noqa: BLE001
            pass


def test() -> tuple[bool, str]:
    if not enabled():
        return False, "не задан токен бота"
    me = _call("getMe")
    if not owner():
        from .dashboard import BRAIN
        code = f"/start {PAIR_CODE}" if BRAIN.get("ask") else "/start и код из окна Джарвиса"
        return True, f"бот @{me['username']} работает. Привяжите его: отправьте боту  {code}"
    send(f"🔔 Проверка связи. К вашим услугам, {config.USER_NAME}.")
    return True, f"бот @{me['username']} работает и привязан — проверочное сообщение отправлено"

