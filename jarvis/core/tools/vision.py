"""Глаза Джарвиса: посмотреть на экран или в камеру — только когда об этом просят.

Идея из adewaskar/jarvis (MIT). Снимок делается один раз, показывается на экране Джарвиса и
отдаётся модели для ответа. Камера включается на долю секунды и сразу выключается; ничего не записывается,
кроме этого одного кадра в data/vision (старые кадры удаляются).
"""
import base64
import os
import time
from datetime import datetime

from .. import activity, config
from . import S, tool

FOLDER = config.DATA_DIR / "vision"


def _cleanup(keep: int = 20):
    files = sorted(FOLDER.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


def grab_screen(path):
    import pyautogui
    img = pyautogui.screenshot()
    img.thumbnail((1600, 1600))
    img.convert("RGB").save(path, "JPEG", quality=85)


def grab_camera(path):
    from .. import gestures
    frame = gestures.last_frame() if gestures.running() else None
    if frame is not None:  # жесты уже держат камеру — берём их кадр, второй раз камеру не открыть
        import cv2
        cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError("для камеры нужен пакет opencv-python: обновите Джарвиса (update_jarvis.bat)") from e
    cap = cv2.VideoCapture(0, getattr(cv2, "CAP_DSHOW", 0)) if os.name == "nt" else cv2.VideoCapture(0)
    try:
        if not cap.isOpened():
            raise RuntimeError("камера не найдена или занята другой программой")
        frame = None
        t = time.time()
        while time.time() - t < 1.5:  # первые кадры тёмные — даём камере выставить экспозицию
            ok, f = cap.read()
            if ok:
                frame = f
        if frame is None:
            raise RuntimeError("камера не отдала кадр")
        cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    finally:
        cap.release()


def analyse(path, question: str) -> str | None:
    """Ответ по картинке через OpenAI (если есть ключ). Без ключа — None: Claude Code посмотрит файл сам."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    import openai
    b64 = base64.b64encode(path.read_bytes()).decode()
    r = openai.OpenAI().chat.completions.create(
        model=config.VISION_MODEL,
        messages=[{"role": "system", "content": "Ты — Джарвис. Отвечай по-русски, коротко и по делу: 1–4 "
                                                "предложения. Если на картинке текст ошибки — процитируй главное."},
                  {"role": "user", "content": [{"type": "text", "text": question or "Что здесь?"},
                                               {"type": "image_url",
                                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        max_tokens=500,
    )
    return (r.choices[0].message.content or "").strip()


@tool("look",
      "Посмотреть на экран компьютера (source=screen) или в веб-камеру (source=camera) и ответить на вопрос о том, "
      "что видно. Экран — «что у меня на экране», «прочитай ошибку», «что тут написано». Камеру включай ТОЛЬКО "
      "когда пользователь прямо просит посмотреть на неё («посмотри на меня», «что у меня в руке») — никогда по "
      "своей инициативе.",
      {"source": S("screen или camera", enum=["screen", "camera"]), "question": S("Что нужно понять по картинке")},
      ["source"])
def look(source: str = "screen", question: str = ""):
    FOLDER.mkdir(exist_ok=True)
    path = FOLDER / f"{source}_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    if source == "camera":
        activity.emit("tool", "Камера включена на секунду", "один кадр по вашей просьбе")
        grab_camera(path)
    else:
        grab_screen(path)
    _cleanup()
    from .screen import show
    show("Камера" if source == "camera" else "Экран", f"*{question}*" if question else "", image=str(path),
         panel_id=f"look-{source}")
    answer = analyse(path, question)
    if answer:
        return answer
    return f"Снимок сохранён: {path}. Открой его (Read) и ответь на вопрос: {question or 'что на нём'}."


@tool("gestures",
      "Управление жестами перед веб-камерой: on — включить (ладонь — стоп, «победа» — слушаю, палец вверх/вниз — "
      "да/нет, кулак — убрать панель, «люблю тебя» — режим курсора), off — выключить и освободить камеру, "
      "pointer_on/pointer_off — водить мышью указательным пальцем, щипок — клик. Включай только по просьбе.",
      {"action": S("on, off, pointer_on, pointer_off", enum=["on", "off", "pointer_on", "pointer_off"])},
      ["action"], in_main=True)
def gestures_tool(action: str):
    from .. import gestures
    if action == "off":
        return gestures.stop()
    if action in ("pointer_on", "pointer_off"):
        msg = gestures.start() if not gestures.running() else ""
        gestures.STATE["pointer"] = action == "pointer_on"
        return (msg + " " if msg else "") + ("Курсор следует за указательным пальцем, щипок — клик."
                                             if action == "pointer_on" else "Курсор снова ваш.")
    return gestures.start()
