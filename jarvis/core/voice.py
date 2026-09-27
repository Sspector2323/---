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
        self.rec.pause_threshold = 0.8
        self.rec.dynamic_energy_threshold = True
        self.mic = sr.Microphone()
        self.lock = threading.Lock()  # чтобы не говорить двумя голосами сразу
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        self._engine = None

    # ---------- Слух ----------
    def listen(self, timeout: float | None = None, phrase_limit: float = 15) -> str | None:
        try:
            with self.mic as src:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
            return self.rec.recognize_google(audio, language="ru-RU").strip()
        except (self.sr.WaitTimeoutError, self.sr.UnknownValueError):
            return None
        except self.sr.RequestError:
            print("⚠ Нет интернета для распознавания речи")
            time.sleep(2)
            return None

    # ---------- Голос ----------
    def say(self, text: str):
        print(f"🤖 Джарвис: {text}")
        if not text:
            return
        with self.lock:
            try:
                self._say_edge(text)
            except Exception as e:  # noqa: BLE001 — нет интернета и т.п.
                print(f"(edge-tts недоступен: {e}; говорю запасным голосом)")
                self._say_offline(text)

    def _say_edge(self, text: str):
        import edge_tts
        import pygame
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            asyncio.run(edge_tts.Communicate(text, config.TTS_VOICE, rate="+8%").save(path))
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _say_offline(self, text: str):
        import pyttsx3
        if self._engine is None:
            self._engine = pyttsx3.init()
            for v in self._engine.getProperty("voices"):
                if "ru" in (v.id + v.name).lower() or "irina" in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break
        self._engine.say(text)
        self._engine.runAndWait()

    def confirm(self, question: str) -> bool:
        self.say(f"Подтвердите: {question[:200]}. Да или нет?")
        answer = (self.listen(timeout=7, phrase_limit=4) or "").lower()
        print(f"🎤 Вы: {answer}")
        return any(w in answer.split() for w in YES)


class TextIO:
    """Режим без микрофона — для проверки и тихой работы."""
    lock = threading.Lock()

    def listen(self, timeout=None, phrase_limit=None) -> str | None:
        try:
            return input("🧑 Вы: ").strip() or None
        except EOFError:
            return "выход"

    def say(self, text: str):
        print(f"🤖 Джарвис: {text}")

    def confirm(self, question: str) -> bool:
        return input(f"❓ {question}\n   Подтвердить? (да/нет): ").strip().lower() in YES
