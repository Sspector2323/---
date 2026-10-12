"""Музыка: заставка при запуске и тихий фон во время долгой задачи.

Треки — Kevin MacLeod, CC BY 4.0 (assets/audio/CREDITS.md). Свои — в data/music/ с теми же именами.
MUSIC=boot — только при запуске (по умолчанию), all — ещё и фон за работой, off — без музыки.
Играет на отдельных каналах и не мешает голосу Джарвиса.
"""
import threading

from . import config

ASSETS = config.ROOT / "assets" / "audio"
_playing: dict = {}
_lock = threading.Lock()


def _file(name: str):
    own = config.DATA_DIR / "music" / f"{name}.mp3"
    return own if own.exists() else ASSETS / f"{name}.mp3"


def play(name: str, volume: float = 0.35, loop: bool = False, fade_ms: int = 600) -> bool:
    if config.MUSIC == "off" or (name == "work" and config.MUSIC != "all"):
        return False
    path = _file(name)
    if not path.exists():
        return False
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        with _lock:
            if name in _playing and _playing[name].get_busy():
                return True
            snd = pygame.mixer.Sound(str(path))
            snd.set_volume(volume)
            _playing[name] = snd.play(loops=-1 if loop else 0, fade_ms=fade_ms)
        return True
    except Exception:  # noqa: BLE001 — нет звуковой карты и т.п.: просто без музыки
        return False


def stop(name: str, fade_ms: int = 900):
    with _lock:
        ch = _playing.pop(name, None)
    if ch is not None:
        try:
            ch.fadeout(fade_ms)
        except Exception:  # noqa: BLE001
            pass


def boot():
    """Заставка: нарастающий аккорд и тихий фон под анимацию появления."""
    play("boot-music", 0.5)
    play("ambient", 0.18)
