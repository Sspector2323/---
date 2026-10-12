"""Звуки интерфейса: «слушаю», «готово», «ошибка», «хлопок принят».

Звуки синтезируются кодом при первом запуске (data/sounds/*.wav) — ничего не надо скачивать.
Хотите свои — положите файлы с теми же именами (wake.wav, done.wav, error.wav, clap.wav) в data/sounds,
и они заиграют вместо встроенных. Идея — из adewaskar/jarvis (MIT).
"""
import array
import math
import wave

from . import config

RATE = 44100
FOLDER = config.DATA_DIR / "sounds"


def _tone(parts, volume=0.32):
    """parts: [(частота, длительность, частота2|None)] — короткие мягкие ноты с плавной атакой и затуханием."""
    out = array.array("h")
    for f1, dur, f2 in parts:
        n = int(RATE * dur)
        phase = 0.0
        for i in range(n):
            f = f1 if not f2 else f1 + (f2 - f1) * i / n
            phase += 2 * math.pi * f / RATE
            env = min(1.0, i / (RATE * 0.006)) * math.exp(-3.2 * i / n)
            v = math.sin(phase) * 0.8 + math.sin(2 * phase) * 0.15 + math.sin(3 * phase) * 0.05
            out.append(int(32767 * volume * env * v))
    return out


SOUNDS = {
    "wake": lambda: _tone([(660, 0.07, None), (990, 0.12, None)]),          # «слушаю»
    "clap": lambda: _tone([(520, 0.06, None), (780, 0.06, None), (1170, 0.12, None)]),
    "done": lambda: _tone([(880, 0.09, None), (1320, 0.22, None)], 0.22),   # тихий звон
    "sleep": lambda: _tone([(880, 0.08, None), (587, 0.16, None)], 0.16),      # «засыпаю» — тихо, вниз
    "error": lambda: _tone([(330, 0.12, None), (220, 0.25, None)], 0.28),
}


def path(name: str):
    FOLDER.mkdir(exist_ok=True)
    p = FOLDER / f"{name}.wav"
    if not p.exists() and name in SOUNDS:
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(SOUNDS[name]().tobytes())
    return p


def play(name: str) -> bool:
    """Играет звук поверх голоса, не прерывая его. False — звуки выключены или недоступны."""
    if not config.SOUNDS:
        return False
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.Sound(str(path(name))).play()
        return True
    except Exception:  # noqa: BLE001
        return False
