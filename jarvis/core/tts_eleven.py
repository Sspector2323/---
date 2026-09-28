"""Голос из ElevenLabs (ваш собственный голос, созданный там в Voice Design или записанный вами)."""
import requests

from . import config

API = "https://api.elevenlabs.io/v1"


def enabled() -> bool:
    return bool(config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID)


def synth_to_file(text: str, path: str) -> str:
    """Озвучить текст голосом ElevenLabs в mp3 (подходит и для колонок, и для голосовых в Телеграме)."""
    speed = max(0.7, min(1.2, config.VOICE_SPEED))  # ElevenLabs принимает темп 0.7–1.2
    r = requests.post(
        f"{API}/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL, "language_code": "ru",
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25,
                                 "use_speaker_boost": True, "speed": speed}},
        timeout=60,
    )
    if r.status_code == 400 and "language_code" in r.text:  # не все модели принимают язык явно
        r = requests.post(f"{API}/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
                          params={"output_format": "mp3_44100_128"},
                          headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                          json={"text": text, "model_id": config.ELEVENLABS_MODEL}, timeout=60)
    if r.status_code == 401:
        raise RuntimeError("ElevenLabs не принял ключ API")
    if r.status_code == 404:
        raise RuntimeError("ElevenLabs не нашёл голос — проверьте Voice ID")
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def voices() -> list[dict]:
    r = requests.get(f"{API}/voices", headers={"xi-api-key": config.ELEVENLABS_API_KEY}, timeout=20)
    r.raise_for_status()
    return [{"id": v["voice_id"], "name": v["name"], "category": v.get("category", "")} for v in r.json().get("voices", [])]
