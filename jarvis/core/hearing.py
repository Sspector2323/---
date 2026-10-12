"""Слух Джарвиса: распознавание, отсев собственного эха, хлопки и диагностика.

Идеи взяты из открытого проекта adewaskar/jarvis (MIT) и переписаны под наш Python-Джарвис:
- точное распознавание ElevenLabs Scribe (если есть ключ ElevenLabs), запасное — Google;
- Джарвис слышит себя из колонок — такие фразы отсеиваются по тексту (сверка со сказанным);
- двойной хлопок будит его без слова «Джарвис» (хлопок узнаём по форме звука, а не по громкости);
- DIAG — живое состояние слуха для карточки «Слух» на дашборде: почему он не слышит, видно сразу.
"""
import array
import math
import re
import time

from . import config

DIAG = {
    "state": "запуск",          # слушаю / говорю / думаю
    "ambient": 0, "threshold": 0,
    "last_level": 0,            # громкость последней услышанной фразы
    "last_text": "", "last_at": 0.0, "last_engine": "", "last_stt": 0.0,
    "echo_drops": 0, "last_echo": "",
    "barge": "",                # чем закончилась последняя попытка перебить
    "claps": 0, "stt_errors": 0, "stt_note": "",
    "last_said": "", "said_at": 0.0,  # что Джарвис сказал последним — для субтитров на 3D-ядре
}

_down_until = 0.0  # Scribe не ответил — 10 минут пользуемся Google


def scribe_enabled() -> bool:
    return bool(config.ELEVENLABS_API_KEY) and config.STT_ENGINE in ("smart", "elevenlabs") \
        and time.time() > _down_until


def transcribe(rec, audio, accurate: bool = False) -> str | None:
    """Текст фразы. accurate=True — это команда Джарвису: берём самый точный движок."""
    import speech_recognition as sr
    global _down_until
    t = time.time()
    use_scribe = scribe_enabled() and (accurate or config.STT_ENGINE == "elevenlabs")
    try:
        if use_scribe:
            try:
                text, engine = _scribe(audio), "ElevenLabs"
            except Exception as e:  # noqa: BLE001
                _down_until = time.time() + 600
                DIAG.update(stt_errors=DIAG["stt_errors"] + 1, stt_note=f"ElevenLabs: {str(e)[:80]} — пока Google")
                print(f"⚠ Распознавание ElevenLabs недоступно ({str(e)[:100]}) — 10 минут слушаю через Google.")
                use_scribe = False
        if not use_scribe:
            try:
                text, engine = rec.recognize_google(audio, language="ru-RU").strip(), "Google"
            except sr.UnknownValueError:
                text, engine = "", "Google"
    finally:
        DIAG["last_stt"] = round(time.time() - t, 2)
    text = _clean(text)
    if text:
        DIAG.update(last_text=text, last_at=time.time(), last_engine=engine)
    return text or None


def _scribe(audio) -> str:
    import requests
    r = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        data={"model_id": config.STT_MODEL, "language_code": "ru", "tag_audio_events": "false"},
        files={"file": ("phrase.wav", audio.get_wav_data(convert_rate=16000), "audio/wav")},
        timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:120]}")
    return (r.json().get("text") or "").strip()


def _clean(text: str) -> str:
    # Scribe иногда подписывает звуки: «(смех)», «[музыка]» — это не слова
    text = re.sub(r"[\(\[][^)\]]{1,30}[\)\]]", "", text or "")
    return re.sub(r"\s{2,}", " ", text).strip(" .")


# ---------- Эхо: Джарвис слышит сам себя ----------
OVERRIDE = re.compile(r"\b(джарвис|джарвиз|jarvis|стоп|хватит|подожди|погоди|замолчи)\b", re.I)
STOP = set("и в во на с со к ко о об от до по за из у не ни но а же ли бы то это как что так вот да нет я вы мы он "
           "она они его её ее их мне вам нам вас нас ваш ваша ваше ваши мой моя моё мои уже ещё еще очень".split())


def _words(text: str) -> list[str]:
    return [w for w in re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е")).split() if w]


def is_echo(heard: str, spoken: str) -> bool:
    """Услышанное — это его же фраза из колонок? Лучше пропустить эхо, чем выбросить ваш вопрос."""
    if not spoken or OVERRIDE.search(heard):
        return False
    words = _words(heard)
    if not words:
        return True
    mine = set(_words(spoken))
    content = [w for w in words if w not in STOP]
    if len(content) < 2:  # ничего характерного — выбрасываем только при полном совпадении
        return len(words) >= 2 and all(w in mine for w in words)
    hits = sum(1 for w in content if w in mine)
    return hits / len(content) >= 0.6


# ---------- Хлопки ----------
def _levels(raw: bytes, rate: int, width: int, ms: int = 5) -> list[float]:
    if width != 2:
        return []
    a = array.array("h", raw)
    n = max(1, int(rate * ms / 1000))
    return [math.sqrt(sum(x * x for x in a[i:i + n]) / n) for i in range(0, len(a) - n + 1, n)]


def count_claps(raw: bytes, rate: int, width: int, floor: float) -> list[float]:
    """Моменты хлопков (сек). Хлопок не громкий, а РЕЗКИЙ: тишина перед ним, взлёт за пару миллисекунд
    и затухание за десятую долю секунды. Речь, музыка и кашель так быстро не гаснут."""
    lv = _levels(raw, rate, width)
    step = 0.005
    claps, i = [], 6
    while i < len(lv) - 2:
        peak = lv[i]
        if peak < max(floor * 4, 900):
            i += 1
            continue
        before = sum(lv[i - 6:i - 1]) / 5
        if before > peak / 5 or lv[i - 1] > peak * 0.6:  # не было тишины или подъём слишком плавный
            i += 1
            continue
        top = max(range(i, min(i + 3, len(lv))), key=lambda k: lv[k])
        tail = lv[top + 1: top + 25]  # 120 мс после пика
        if tail and min(tail) < lv[top] * 0.15 and sum(tail[-6:]) / max(1, len(tail[-6:])) < lv[top] * 0.25:
            claps.append(top * step)
            i = top + 30  # 150 мс — один хлопок = одно событие
        else:
            i = top + 1
    return claps


def is_double_clap(raw: bytes, rate: int, width: int, floor: float) -> bool:
    lv = _levels(raw, rate, width)
    if not lv or len(lv) * 0.005 > 3.0:
        return False
    loud = sum(1 for x in lv if x > max(floor * 2, 400)) / len(lv)
    if loud > 0.2:  # долгий звук (речь, музыка) — это не хлопки
        return False
    c = count_claps(raw, rate, width, floor)
    return any(0.15 <= b - a <= 1.0 for a, b in zip(c, c[1:]))


def phrase_level(raw: bytes, rate: int, width: int) -> int:
    """Громкость фразы (90-й перцентиль) — чтобы на дашборде было видно, насколько вы выше порога."""
    lv = sorted(_levels(raw, rate, width, ms=30) or [0])
    return int(lv[int(len(lv) * 0.9)])
