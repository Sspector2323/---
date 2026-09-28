"""Слух (распознавание речи) и голос (синтез речи)."""
import asyncio
import os
import tempfile
import threading
import time

from . import config

YES = ("да", "подтверждаю", "давай", "выполняй", "конечно", "ок", "окей", "угу", "ага", "yes", "делай")


class Voice:
    def __init__(self):
        import speech_recognition as sr
        self.sr = sr
        self.rec = sr.Recognizer()
        # через сколько секунд тишины фраза считается законченной (меньше = быстрее реакция)
        self.rec.pause_threshold = config.PAUSE_SECONDS
        self.rec.non_speaking_duration = min(0.5, config.PAUSE_SECONDS)
        self.rec.dynamic_energy_threshold = True
        self.mic = sr.Microphone()
        self.lock = threading.Lock()  # чтобы не говорить двумя голосами сразу
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        self._engine = None
        self.last_stt = 0.0
        try:  # заранее включаем звук, чтобы не тратить на это время при первом ответе
            import pygame
            pygame.mixer.init()
        except Exception:  # noqa: BLE001
            pass

    def beep(self):
        """Короткий сигнал «слушаю» — мгновенно, без синтеза речи."""
        try:
            import winsound
            winsound.Beep(880, 120)
        except Exception:  # noqa: BLE001 — не Windows
            print("\a", end="", flush=True)

    # ---------- Слух ----------
    def listen(self, timeout: float | None = None, phrase_limit: float = 45) -> str | None:
        try:
            with self.mic as src:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
            t = time.time()
            try:
                return self.rec.recognize_google(audio, language="ru-RU").strip()
            finally:
                self.last_stt = time.time() - t
        except (self.sr.WaitTimeoutError, self.sr.UnknownValueError):
            return None
        except self.sr.RequestError:
            print("⚠ Нет интернета для распознавания речи")
            time.sleep(2)
            return None

    # ---------- Голос ----------
    # Порядок: edge (бесплатный голос Microsoft) → openai (платный, стабильный, если есть ключ) → голос Windows.
    # Движок, который не ответил, пропускаем 10 минут — чтобы не ждать его на каждой фразе.
    _down: dict = {}

    def _engines(self) -> list[str]:
        pref = config.TTS_ENGINE
        order = {"edge": ["edge", "openai"], "openai": ["openai", "edge"]}.get(pref, ["edge", "openai"])
        return [e for e in order if not (e == "openai" and not os.getenv("OPENAI_API_KEY"))
                and self._down.get(e, 0) < time.time()]

    confirming = False  # идёт голосовое подтверждение — перебивки молчат

    def _cache_path(self, text: str):
        import hashlib
        folder = config.DATA_DIR / "tts_cache"
        folder.mkdir(exist_ok=True)
        key = hashlib.md5(f"{config.TTS_ENGINE}|{config.TTS_VOICE}|{config.OPENAI_VOICE}|{config.VOICE_SPEED}|"
                          f"{config.VOICE_PITCH}|{config.VOICE_STYLE}|{text}".encode()).hexdigest()
        return folder / f"{key}.mp3"

    def prewarm(self, phrases):
        """Заранее озвучить частые фразы (перебивки) — потом они звучат мгновенно."""
        import shutil
        for text in phrases:
            target = self._cache_path(text)
            if target.exists():
                continue
            for engine in self._engines():
                try:
                    shutil.move(getattr(self, f"_synth_{engine}")(text), target)
                    break
                except Exception:  # noqa: BLE001
                    continue

    def say(self, text: str, cache: bool = False, quiet: bool = False):
        if not quiet:
            print(f"🤖 Джарвис: {text}")
        from .speech import for_speech
        text = for_speech(text)  # ссылки, пути и разметку не читаем — они на экране
        if not text:
            return
        cached = self._cache_path(text) if cache else None
        with self.lock:
            if cached and cached.exists():
                self._play(str(cached), keep=True)
                return
            for engine in self._engines():
                try:
                    path = getattr(self, f"_synth_{engine}")(text)
                    if cached:
                        import shutil
                        shutil.copy(path, cached)
                    self._play(path)
                    return
                except Exception as e:  # noqa: BLE001
                    self._down[engine] = time.time() + 600
                    print(f"⚠ Голос {engine} недоступен ({type(e).__name__}: {str(e)[:120]}) — пробую следующий.")
            if config.OFFLINE_VOICE:
                self._say_offline(text)

    def _synth_edge(self, text: str) -> str:
        import edge_tts
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        rate = f"{round((config.VOICE_SPEED - 1) * 100):+d}%"
        asyncio.run(edge_tts.Communicate(text, config.TTS_VOICE, rate=rate, pitch=config.VOICE_PITCH).save(path))
        if os.path.getsize(path) == 0:
            raise RuntimeError("пустой звук")
        return path

    def _synth_openai(self, text: str) -> str:
        import openai
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        client = self.__dict__.setdefault("_openai", openai.OpenAI())
        params = dict(model="gpt-4o-mini-tts", voice=config.OPENAI_VOICE, input=text, response_format="mp3",
                      instructions=config.VOICE_STYLE, speed=config.VOICE_SPEED)
        try:
            with client.audio.speech.with_streaming_response.create(**params) as r:
                r.stream_to_file(path)
        except openai.BadRequestError:  # если модель не принимает speed — темп задаём только инструкцией
            params.pop("speed")
            with client.audio.speech.with_streaming_response.create(**params) as r:
                r.stream_to_file(path)
        return path

    def _play(self, path: str, keep: bool = False):
        import pygame
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()
        finally:
            if not keep:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _say_offline(self, text: str):
        import pyttsx3
        if self._engine is None:
            self._engine = pyttsx3.init()
            voices = self._engine.getProperty("voices")
            russian = [v for v in voices if any(k in (v.id + v.name).lower() for k in ("ru", "irina", "pavel"))]
            # мужской (Pavel) в приоритете; если в Windows есть только Irina — будет женский
            male = [v for v in russian if "pavel" in v.name.lower() or getattr(v, "gender", "") == "male"]
            if male or russian:
                self._engine.setProperty("voice", (male or russian)[0].id)
        self._engine.say(text)
        self._engine.runAndWait()

    def confirm(self, question: str) -> bool:
        self.confirming = True
        try:
            self.say(f"Подтвердите: {question[:200]}. Да или нет?")
            answer = (self.listen(timeout=7, phrase_limit=4) or "").lower()
            print(f"🎤 Вы: {answer}")
            return any(w in answer.split() for w in YES)
        finally:
            self.confirming = False


class TextIO:
    """Режим без микрофона — для проверки и тихой работы."""
    lock = threading.Lock()

    last_stt = 0.0
    confirming = False

    def beep(self):
        pass

    def prewarm(self, phrases):
        pass

    def listen(self, timeout=None, phrase_limit=None) -> str | None:
        try:
            return input("🧑 Вы: ").strip() or None
        except EOFError:
            return "выход"

    def say(self, text: str, cache: bool = False, quiet: bool = False):
        print(f"🤖 Джарвис: {text}" if not quiet else f"   … {text}")

    def confirm(self, question: str) -> bool:
        return input(f"❓ {question}\n   Подтвердить? (да/нет): ").strip().lower() in YES
