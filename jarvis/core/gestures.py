"""Жесты рукой перед веб-камерой. Идея из adewaskar/jarvis (MIT), здесь — на MediaPipe в Python.

Включается только по вашей просьбе («Джарвис, включи жесты») или настройкой GESTURES=true; пока жесты
включены, камера работает, а на дашборде горит индикатор. Кадры никуда не отправляются и не сохраняются —
распознавание идёт на компьютере.

   ✋ ладонь        — «стоп»: замолчать и бросить текущую задачу
   ✌️ «победа»      — слушаю (как слово «Джарвис»)
   👍 большой палец — «да» на вопрос-подтверждение
   👎 палец вниз    — «нет»
   ✊ кулак          — убрать верхнюю панель с экрана
   🤟 «люблю тебя»  — включить/выключить управление курсором
   ☝️ указательный  — в режиме курсора водит мышью; щипок (большой + указательный) — клик
"""
import math
import threading
import time

from . import config

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/"
             "float16/1/gesture_recognizer.task")
NAMES = {"Open_Palm": "ладонь", "Victory": "победа", "Thumb_Up": "палец вверх", "Thumb_Down": "палец вниз",
         "Closed_Fist": "кулак", "ILoveYou": "«люблю тебя»", "Pointing_Up": "указательный"}
HOLD = 0.45      # столько жест держится, прежде чем сработать (случайные движения не считаются)
COOLDOWN = 1.6   # после срабатывания — пауза, чтобы один жест = одно действие

STATE = {"on": False, "hand": False, "gesture": "", "pointer": False, "note": "", "last_action": ""}
HANDLERS: dict = {}   # stop, wake, yes, no, close_panel — задаёт main.py
_thread = None
_stop = threading.Event()
_frame_lock = threading.Lock()
_last_frame = None


def last_frame():
    """Последний кадр камеры (BGR) — инструмент look берёт его, пока жесты включены, чтобы не спорить за камеру."""
    with _frame_lock:
        return None if _last_frame is None else _last_frame.copy()


def running() -> bool:
    return _thread is not None and _thread.is_alive()


def _model_path():
    path = config.DATA_DIR / "gesture_recognizer.task"
    if not path.exists():
        import requests
        STATE["note"] = "скачиваю модель жестов (8 МБ)…"
        r = requests.get(MODEL_URL, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


class OneEuro:
    """Сглаживание курсора: на медленных движениях убирает дрожь, на быстрых не отстаёт."""
    def __init__(self, min_cutoff=1.2, beta=0.02):
        self.min_cutoff, self.beta, self.x, self.dx, self.t = min_cutoff, beta, None, 0.0, None

    @staticmethod
    def _a(cutoff, dt):
        r = 2 * math.pi * cutoff * dt
        return r / (r + 1)

    def __call__(self, x, t):
        if self.x is None:
            self.x, self.t = x, t
            return x
        dt = max(1e-3, t - self.t)
        dx = (x - self.x) / dt
        self.dx += self._a(1.0, dt) * (dx - self.dx)
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        self.x += self._a(cutoff, dt) * (x - self.x)
        self.t = t
        return self.x


def _fire(name: str):
    action = {"Open_Palm": "stop", "Victory": "wake", "Thumb_Up": "yes", "Thumb_Down": "no",
              "Closed_Fist": "close_panel"}.get(name)
    if name == "ILoveYou":
        STATE["pointer"] = not STATE["pointer"]
        STATE["last_action"] = f"курсор {'включён' if STATE['pointer'] else 'выключен'}"
        return
    fn = HANDLERS.get(action)
    if fn:
        STATE["last_action"] = f"{NAMES.get(name, name)} → {action}"
        try:
            from . import activity
            activity.emit("voice", f"Жест: {NAMES.get(name, name)}", action)
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"(жест {name}: {e})")


def _loop():
    global _last_frame
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    try:
        recognizer = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
            base_options=BaseOptions(model_asset_path=str(_model_path())),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=0.6, min_tracking_confidence=0.5))
    except Exception as e:  # noqa: BLE001
        STATE.update(on=False, note=f"не запустились: {e}"[:160])
        return
    import os
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
    if not cap.isOpened():
        STATE.update(on=False, note="камера не найдена или занята")
        recognizer.close()
        return
    screen_w, screen_h = _screen_size()
    fx, fy = OneEuro(), OneEuro()
    current, since, fired_at, pinched = "", 0.0, 0.0, False
    STATE.update(on=True, note="камера включена")
    t0 = time.time()
    try:
        while not _stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            with _frame_lock:
                _last_frame = frame
            small = cv2.resize(frame, (480, int(480 * frame.shape[0] / frame.shape[1])))
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
            now = time.time()
            result = recognizer.recognize_for_video(image, int((now - t0) * 1000))
            hand = bool(result.hand_landmarks)
            name = ""
            if result.gestures and result.gestures[0] and result.gestures[0][0].score > 0.6:
                name = result.gestures[0][0].category_name
                name = "" if name == "None" else name
            STATE.update(hand=hand, gesture=NAMES.get(name, ""))
            if STATE["pointer"] and hand:
                lm = result.hand_landmarks[0]
                # рабочая зона — середина кадра; зеркалим по горизонтали, как в зеркале
                x = min(1.0, max(0.0, (1 - lm[8].x - 0.2) / 0.6))
                y = min(1.0, max(0.0, (lm[8].y - 0.2) / 0.6))
                size = math.dist((lm[0].x, lm[0].y), (lm[9].x, lm[9].y)) or 1
                pinch = math.dist((lm[4].x, lm[4].y), (lm[8].x, lm[8].y)) / size < 0.25
                _move(fx(x * screen_w, now), fy(y * screen_h, now))
                if pinch and not pinched:
                    _click()
                pinched = pinch
                if name in ("Pointing_Up", ""):
                    continue  # в режиме курсора указательный — это мышь, а не команда
            if name != current:
                current, since = name, now
            elif name and now - since >= HOLD and now - fired_at >= COOLDOWN:
                fired_at = now
                _fire(name)
            time.sleep(0.02)
    finally:
        cap.release()
        recognizer.close()
        with _frame_lock:
            _last_frame = None
        STATE.update(on=False, hand=False, gesture="", note="камера выключена")


def _screen_size():
    try:
        import pyautogui
        return pyautogui.size()
    except Exception:  # noqa: BLE001
        return 1920, 1080


def _move(x, y):
    try:
        import pyautogui
        pyautogui.moveTo(int(x), int(y), _pause=False)
    except Exception:  # noqa: BLE001
        pass


def _click():
    try:
        import pyautogui
        pyautogui.click(_pause=False)
        STATE["last_action"] = "щипок → клик"
    except Exception:  # noqa: BLE001
        pass


def start() -> str:
    global _thread
    if running():
        return "Жесты уже включены."
    try:
        import cv2  # noqa: F401
        import mediapipe  # noqa: F401
    except ImportError:
        return "Для жестов нужны пакеты mediapipe и opencv-python — запустите update_jarvis.bat."
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="jarvis-gestures")
    _thread.start()
    for _ in range(60):  # ждём камеру и модель — до 6 секунд
        if STATE["on"] or not _thread.is_alive():
            break
        time.sleep(0.1)
    return "Жесты включены: ладонь — стоп, «победа» — слушаю, палец вверх — да." if STATE["on"] else \
        f"Жесты не включились: {STATE['note'] or 'камера не ответила'}"


def stop() -> str:
    _stop.set()
    if _thread:
        _thread.join(3)
    STATE["pointer"] = False
    return "Жесты выключены, камера свободна."
