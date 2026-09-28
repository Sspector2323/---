"""Слух (распознавание речи) и голос (синтез речи)."""
import asyncio
import os
import tempfile
import threading
import time

from . import config

YES = ("да", "подтверждаю", "давай", "выполняй", "конечно", "ок", "окей", "угу", "ага", "yes", "делай")


def _sentences(text: str) -> list[str]:
    """Режем на куски по предложениям (не слишком мелкие), чтобы начинать говорить быстрее."""
    import re
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.!?…])\s+", text.strip()):
        buf = f"{buf} {sent}".strip()
        if len(buf) >= (15 if not parts else 90):  # первая фраза короткая — чтобы заговорить сразу
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts or [text]


class Voice:
    def __init__(self):
        import speech_recognition as sr
        self.sr = sr
        self.rec = sr.Recognizer()
        # через сколько секунд тишины фраза считается законченной (меньше = быстрее реакция)
        self.rec.pause_threshold = config.PAUSE_SECONDS
        self.rec.non_speaking_duration = min(0.5, config.PAUSE_SECONDS)
        # Порог НЕ плавает: «динамический» порог после каждой реплики Джарвиса из колонок ползёт вверх,
        # и приходится кричать. Меряем тишину комнаты один раз и держим порог фиксированным.
        self.rec.dynamic_energy_threshold = False
        self.mic = sr.Microphone()
        self.lock = threading.Lock()  # чтобы не говорить двумя голосами сразу
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        self.ambient = self.rec.energy_threshold
        self._set_threshold()
        print(f"🎙 Шум комнаты {self.ambient:.0f}, порог микрофона {self.rec.energy_threshold:.0f}")
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

    def _set_threshold(self):
        """Порог = шум комнаты с небольшим запасом, делённый на «Чувствительность микрофона»."""
        sens = max(0.3, config.MIC_SENSITIVITY)
        self.rec.energy_threshold = min(1500.0, max(60.0, max(self.ambient * 1.4, 120.0) / sens))

    # ---------- Слух ----------
    def listen(self, timeout: float | None = None, phrase_limit: float = 45) -> str | None:
        self._set_threshold()  # чувствительность можно менять в настройках на ходу
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
        from . import tts_eleven
        pref = config.TTS_ENGINE
        order = {"edge": ["edge", "openai", "elevenlabs"], "openai": ["openai", "elevenlabs", "edge"],
                 "elevenlabs": ["elevenlabs", "openai", "edge"]}.get(pref, ["edge", "openai"])
        available = {"openai": bool(os.getenv("OPENAI_API_KEY")), "elevenlabs": tts_eleven.enabled(), "edge": True}
        return [e for e in order if available[e] and self._down.get(e, 0) < time.time()]

    confirming = False  # идёт голосовое подтверждение — перебивки молчат

    def _cache_path(self, text: str):
        import hashlib
        folder = config.DATA_DIR / "tts_cache"
        folder.mkdir(exist_ok=True)
        key = hashlib.md5(f"{config.TTS_ENGINE}|{config.TTS_VOICE}|{config.OPENAI_VOICE}|{config.ELEVENLABS_VOICE_ID}|"
                          f"{config.ELEVENLABS_MODEL}|{config.VOICE_SPEED}|"
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

    barge_text: str | None = None  # что вы сказали, перебив Джарвиса (обрабатывается как новая команда)

    def _synth(self, text: str) -> str | None:
        for engine in self._engines():
            try:
                return getattr(self, f"_synth_{engine}")(text)
            except Exception as e:  # noqa: BLE001
                self._down[engine] = time.time() + 600
                print(f"⚠ Голос {engine} недоступен ({type(e).__name__}: {str(e)[:120]}) — пробую следующий.")
        return None

    def say(self, text: str, cache: bool = False, quiet: bool = False):
        if not quiet:
            print(f"🤖 Джарвис: {text}")
        from .speech import for_speech
        text = for_speech(text)  # ссылки, пути и разметку не читаем — они на экране
        if not text:
            return
        self.barge_text = None
        cached = self._cache_path(text) if cache else None
        with self.lock:
            if cached and cached.exists():
                self._play(str(cached), keep=True)
                return
            if cached:  # короткая фраза-перебивка: целиком и в кэш
                path = self._synth(text)
                if path:
                    import shutil
                    shutil.copy(path, cached)
                    self._play(path)
                elif config.OFFLINE_VOICE:
                    self._say_offline(text)
                return
            # длинный ответ — по предложениям: пока звучит одно, следующее уже озвучивается
            parts = _sentences(text)
            box: dict = {}
            nxt = threading.Thread(target=lambda: box.update(p=self._synth(parts[0])))
            nxt.start()
            for i in range(len(parts)):
                nxt.join()
                path = box.get("p")
                if i + 1 < len(parts):
                    box = {}
                    nxt = threading.Thread(target=lambda j=i + 1, b=box: b.update(p=self._synth(parts[j])))
                    nxt.start()
                if path:
                    self._play(path)
                elif config.OFFLINE_VOICE:
                    self._say_offline(parts[i])
                if self.barge_text is not None:  # перебили — остальное не говорим
                    break

    def _synth_edge(self, text: str) -> str:
        import edge_tts
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        rate = f"{round((config.VOICE_SPEED - 1) * 100):+d}%"
        asyncio.run(edge_tts.Communicate(text, config.TTS_VOICE, rate=rate, pitch=config.VOICE_PITCH).save(path))
        if os.path.getsize(path) == 0:
            raise RuntimeError("пустой звук")
        return path

    def _synth_elevenlabs(self, text: str) -> str:
        from . import tts_eleven
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        return tts_eleven.synth_to_file(text, path)

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
            if config.BARGE_IN and not self.confirming:
                self._watch_barge_in(pygame)
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()
        finally:
            if not keep:
                try:
                    os.remove(path)
                except OSError:
                    pass

    STOP_TRIGGERS = ("стоп", "хватит", "подожди", "погоди", "замолчи", "стой", "тихо", "отмена")

    def _barge_words(self, text: str) -> tuple[bool, str]:
        """Есть ли в услышанном обращение («Джарвис…», «стоп»)? И что осталось после него (новая команда)."""
        import re
        words = [w for w in config.WAKE_WORDS if w] + ["джарвиз", "жарвис"]
        low = text.lower()
        hits = [m.start() for w in words + list(self.STOP_TRIGGERS)
                for m in re.finditer(rf"\b{re.escape(w)}\b", low)]
        if not hits:
            return False, ""
        rest = text[min(hits):]
        for w in words:
            rest = re.sub(rf"\b{re.escape(w)}\b[,!.]?", "", rest, flags=re.I)
        stops = "|".join(self.STOP_TRIGGERS)
        rest = re.sub(rf"^[\s,.!]*(?:(?:{stops})\b[\s,.!]*)+", "", rest, flags=re.I)
        return True, rest.strip(" ,.!")

    def _watch_barge_in(self, pygame):
        """Пока Джарвис говорит — слушаем микрофон.
        word-режим (по умолчанию): услышали голос громче эха — НЕ замолкаем сразу, а тихо распознаём пару секунд.
        Замолкаем, только если там «Джарвис…», «стоп», «хватит», «подожди». Так его собственный голос из колонок
        и фоновые разговоры больше не обрывают ответ. any-режим — замолкает от любого громкого голоса."""
        import array
        import math
        from collections import deque

        def rms(chunk: bytes) -> float:
            a = array.array("h", chunk)
            return math.sqrt(sum(x * x for x in a) / max(1, len(a)))

        def recognize(frames) -> str:
            audio = self.sr.AudioData(b"".join(frames), src.SAMPLE_RATE, src.SAMPLE_WIDTH)
            try:
                return self.rec.recognize_google(audio, language="ru-RU").strip()
            except (self.sr.UnknownValueError, self.sr.RequestError):
                return ""

        def drain():  # пока распознавали, в буфере накопился старый звук — выкидываем
            try:
                stream = src.stream.pyaudio_stream
                while stream.get_read_available() >= src.CHUNK:
                    stream.read(src.CHUNK, exception_on_overflow=False)
            except Exception:  # noqa: BLE001
                pass

        def rest_of_phrase() -> str:  # Джарвис замолчал — дослушиваем команду до конца
            try:
                audio = self.rec.listen(src, timeout=1.2, phrase_time_limit=30)
                return self.rec.recognize_google(audio, language="ru-RU").strip()
            except Exception:  # noqa: BLE001
                return ""

        any_voice = config.BARGE_MODE == "any"
        try:
            with self.mic as src:
                chunk_sec = src.CHUNK / src.SAMPLE_RATE
                base = max(self.rec.energy_threshold, 150) * config.BARGE_SENSITIVITY
                levels = deque(maxlen=int(3 / chunk_sec))  # громкость эха за последние 3 секунды
                pre = deque(maxlen=int(0.6 / chunk_sec))
                started, loud = time.time(), 0
                while pygame.mixer.music.get_busy():
                    data = src.stream.read(src.CHUNK)
                    level = rms(data)
                    pre.append(data)
                    if time.time() - started < 0.4 or not levels:
                        levels.append(level)
                        continue
                    # эхо меряем всё время ответа, а не только в первые полсекунды (там в mp3 ещё тишина)
                    echo = sorted(levels)[int(len(levels) * 0.9)]
                    trigger = max(base, echo * 1.5)
                    if level <= trigger:
                        levels.append(level)
                        loud = 0
                        continue
                    loud += 1
                    if loud * chunk_sec < 0.25:
                        continue
                    frames = list(pre)
                    if any_voice:
                        pygame.mixer.music.stop()
                        frames += [src.stream.read(src.CHUNK) for _ in range(int(0.3 / chunk_sec))]
                        heard = recognize(frames)
                        more = rest_of_phrase()
                        self.barge_text = f"{heard} {more}".strip()
                        print(f"✋ Перебили: {self.barge_text or '(не разобрал)'}")
                        return
                    # word-режим: Джарвис продолжает говорить, а мы слушаем ~2 секунды и ищем слово-обращение
                    quiet, t0 = 0.0, time.time()
                    while pygame.mixer.music.get_busy() and time.time() - t0 < 2.2:
                        data = src.stream.read(src.CHUNK)
                        frames.append(data)
                        quiet = quiet + chunk_sec if rms(data) <= trigger else 0.0
                        if quiet >= 0.5 and time.time() - t0 > 0.8:
                            break
                    heard = recognize(frames)
                    hit, rest = self._barge_words(heard) if heard else (False, "")
                    if not hit:
                        if heard:
                            print(f"   (слышу «{heard[:60]}» — это не мне, продолжаю)")
                        drain()
                        pre.clear()
                        loud = 0
                        continue
                    pygame.mixer.music.stop()
                    more = rest_of_phrase()
                    self.barge_text = f"{rest} {more}".strip()
                    print(f"✋ Перебили: {heard}{' ' + more if more else ''}")
                    return
        except Exception as e:  # noqa: BLE001 — микрофон занят и т.п.: просто говорим дальше
            print(f"(перебивание недоступно: {e})")

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
    barge_text = None

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
