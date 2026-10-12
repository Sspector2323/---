"""Живой голос Джарвиса: OpenAI Realtime — слушает и говорит сам, отвечает за доли секунды, с интонацией.

Как устроено:
- Одно постоянное соединение (переподключается само; сессия живёт до 60 минут).
- В режиме ожидания микрофон слушает старый «слух» (слово «Джарвис», хлопок, жест, клавиша) — платные
  минуты не тратятся на разговоры в комнате. Как только к нему обратились, начинается живой разговор:
  звук идёт в модель напрямую, ответ звучит по мере генерации, перебивать можно в любой момент.
  После REALTIME_IDLE секунд тишины он снова «засыпает» до слова «Джарвис».
- Эхо из колонок: пока Джарвис говорит, в модель уходит только звук заметно громче его собственного голоса
  (вы его перебиваете). В наушниках этот фильтр можно выключить: REALTIME_ECHO_GATE=false.
- Инструменты те же, что у обычного мозга. Опасные действия он подтверждает голосом: сначала спрашивает,
  потом вызывает инструмент с confirmed=true. Долгие задачи (Claude Code) идут в фоне, о результате он
  скажет сам, когда будет готово.
"""
import asyncio
import base64
import json
import threading
import time
from collections import deque
from datetime import datetime

from . import activity, config, hearing, storage

RATE = 24000
BYTES_PER_MS = RATE * 2 // 1000  # 16 бит моно
CHUNK = 480                      # 20 мс

PERSONA = """Ты — Джарвис, личный ИИ-ассистент в духе J.A.R.V.I.S. из «Железного человека», живёшь на компьютере
хозяйки и говоришь с ней голосом в реальном времени. Хозяйка — {user}; обращайся по имени и на «вы», о ней —
в женском роде.

Голос и манера: низкий, бархатный, спокойный мужской голос британского дворецкого. Говори живо и выразительно —
с теплом, лёгкой иронией, паузами, улыбкой в голосе; меняй интонацию по смыслу (удивление, сочувствие, азарт).
Никакой монотонности и канцелярита. Отвечай коротко: обычно одна-две фразы, как в живом разговоре.
Если тебя перебили — сразу переключайся на новое, не договаривай старое.

Правила:
- Говори по-русски. Не произноси вслух ссылки, пути к файлам, id и названия инструментов.
- Всё, что удобнее увидеть (списки, таблицы, ссылки, цифры), выводи на экран через show_on_screen, а вслух
  скажи одну фразу.
- Перед инструментом, который займёт время, скажи пару слов («Сейчас посмотрю»), потом вызывай его.
- Опасные действия: если инструмент ответил, что нужно подтверждение, спроси её голосом коротко
  («Выключить компьютер?»). Если она согласна — вызови тот же инструмент ещё раз с confirmed=true.
- Большие задачи (код, сайты, документы, глубокий анализ, разбор почты) — delegate_to_claude: он работает
  в фоне, а ты одной фразой скажи, что поручил это, и продолжай разговор. Когда придёт результат, коротко сообщи.
- Сообщения с пометкой [Система] — служебные: результаты фоновых задач, напоминания. Озвучь суть коротко.
- Почту разбирай только через organize_email / search_email / mark_email.
- Переписки из рабочих чатов — личное: говори только о задачах и сроках.

Сейчас {now}.
Что ты помнишь о хозяйке:
{memory}"""


def _now() -> str:
    from .tools.info import DAYS
    n = datetime.now()
    return f"{n:%Y-%m-%d %H:%M}, {DAYS[n.weekday()]}"


class Realtime:
    def __init__(self, tools: dict, confirm=None, on_status=print):
        self.tools = tools
        self.on_status = on_status
        self.confirm = confirm
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conn = None
        self.ready = threading.Event()
        self.active = False                 # идёт разговор: микрофон уходит в модель
        self.asleep = threading.Event()
        self.asleep.set()
        self.last_voice = 0.0               # когда последний раз было ваше слово или его ответ
        self.out = bytearray()              # звук ответа, ещё не проигранный
        self.out_lock = threading.Lock()
        self.cur_item: str | None = None
        self.cur_played = 0                 # сколько байт текущего ответа уже прозвучало
        self.playing_until = 0.0
        self.pending_calls = 0
        self.said = ""
        self._mic_q: asyncio.Queue | None = None
        self._pre = deque(maxlen=15)        # 300 мс перед началом перебивания
        self._echo = deque(maxlen=150)      # громкость эха за 3 с
        self._loud = 0
        self._gate_open_until = 0.0
        self._ambient = 300.0
        self._announce_done: dict = {}
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-realtime")
        self._thread.start()
        threading.Thread(target=self._watch_idle, daemon=True, name="jarvis-realtime-idle").start()

    def _watch_idle(self):
        while True:
            time.sleep(0.5)
            if self.idle_check():
                from . import sfx
                sfx.play("sleep")
                self.sleep()

    # ---------- публичное ----------
    def converse(self, text: str | None = None, wait: bool = True):
        """Начать живой разговор (и, если есть, сразу ответить на сказанную фразу). Ждёт, пока он «уснёт»."""
        if not self.ready.wait(10):
            raise RuntimeError("живой голос не подключился")
        self.activate()
        if text:
            hearing.DIAG.update(last_text=text, last_at=time.time(), last_engine="Google")
            storage.log("user", text)
            self._send({"type": "conversation.item.create", "item": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}})
            self._send({"type": "response.create"})
        if wait:
            self.asleep.wait()

    def activate(self):
        if not self.active:
            self._send({"type": "session.update", "session": {"type": "realtime", "instructions": self._instructions()}})
            self._send({"type": "input_audio_buffer.clear"})
        self.active = True
        self.asleep.clear()
        self.last_voice = time.time()
        hearing.DIAG["state"] = "слушаю"

    def sleep(self):
        self.active = False
        self.asleep.set()
        hearing.DIAG["state"] = "жду «Джарвис»"

    def interrupt(self):
        """Замолчать сразу (ладонь, Ctrl+Alt+X): отменить ответ и выбросить недоигранный звук."""
        self._send({"type": "response.cancel"})
        self._truncate()

    def announce(self, text: str, timeout: float = 60) -> bool:
        """Сказать готовую фразу своим живым голосом (приветствие, напоминание) — вне разговора."""
        if not self.ready.is_set():
            return False
        key = f"a{time.time_ns()}"
        done = threading.Event()
        self._announce_done[key] = done
        self._send({"type": "response.create", "response": {
            "conversation": "none", "metadata": {"announce": key}, "input": [],
            "instructions": ("Произнеси дословно, ничего не добавляя, живо и с интонацией дворецкого: «"
                             + text.replace("«", "\"").replace("»", "\"") + "»")}})
        deadline = time.time() + timeout
        if not done.wait(timeout):
            self._announce_done.pop(key, None)
            return False
        while self.speaking() and time.time() < deadline:  # дожидаемся, пока прозвучит
            time.sleep(0.05)
        return True

    def inject(self, text: str):
        """Служебное сообщение в разговор (фоновая задача готова) — он сам коротко его озвучит."""
        self._send({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": f"[Система] {text}"}]}})
        self._send({"type": "response.create"})
        self.last_voice = time.time()

    def speaking(self) -> bool:
        with self.out_lock:
            return bool(self.out) or time.time() < self.playing_until

    # ---------- соединение ----------
    def _send(self, event: dict):
        if self.loop and self.conn:
            asyncio.run_coroutine_threadsafe(self.conn.send(event), self.loop)

    def _instructions(self) -> str:
        from .tools.tasks import memory_text
        return PERSONA.format(user=config.USER_NAME, now=_now(), memory=memory_text() or "пока ничего")

    def _tool_schemas(self) -> list[dict]:
        out = []
        for t in self.tools.values():
            params = json.loads(json.dumps(t.schema()["input_schema"]))
            if t.dangerous:
                params.setdefault("properties", {})["confirmed"] = {
                    "type": "boolean", "description": "true — хозяйка уже подтвердила голосом"}
            out.append({"type": "function", "name": t.name, "description": t.description[:1000],
                        "parameters": params})
        out.append({"type": "function", "name": "delegate_to_claude",
                    "description": "Поручить большую задачу Claude Code (код, сайты, документы, разбор почты, анализ, "
                                   "многошаговые дела). Работает в фоне; результат придёт сообщением [Система].",
                    "parameters": {"type": "object", "properties": {"task": {"type": "string", "description":
                                   "Полная формулировка задачи с контекстом"}}, "required": ["task"]}})
        return out

    def _session(self) -> dict:
        vad = ({"type": "semantic_vad", "eagerness": config.REALTIME_EAGERNESS, "create_response": True,
                "interrupt_response": True} if config.REALTIME_VAD == "semantic" else
               {"type": "server_vad", "threshold": 0.55, "prefix_padding_ms": 300, "silence_duration_ms": 450,
                "create_response": True, "interrupt_response": True})
        return {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": self._instructions(),
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": RATE}, "turn_detection": vad,
                          "transcription": {"model": "gpt-4o-mini-transcribe", "language": "ru"},
                          "noise_reduction": {"type": config.REALTIME_NOISE}},
                "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": config.REALTIME_VOICE,
                           "speed": config.REALTIME_SPEED},
            },
            "tools": self._tool_schemas(),
            "tool_choice": "auto",
        }

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self):
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        self._mic_q = asyncio.Queue(maxsize=200)
        self._start_audio()
        backoff = 1
        while True:
            try:
                async with client.realtime.connect(model=config.REALTIME_MODEL) as conn:
                    await conn.session.update(session=self._session())
                    self.conn = conn
                    self.ready.set()
                    backoff = 1
                    started = time.time()
                    sender = asyncio.create_task(self._pump_mic())
                    try:
                        async for event in conn:
                            await self._on_event(event)
                            if time.time() - started > 55 * 60 and not self.active and not self.speaking():
                                break  # сессия живёт 60 минут — переподключаемся заранее, в тишине
                    finally:
                        sender.cancel()
            except Exception as e:  # noqa: BLE001
                self.on_status(f"⚠ Живой голос: {type(e).__name__}: {str(e)[:160]} — переподключаюсь")
                hearing.DIAG["stt_note"] = f"живой голос: {str(e)[:80]}"
            self.ready.clear()
            self.conn = None
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _pump_mic(self):
        while True:
            data = await self._mic_q.get()
            await self.conn.input_audio_buffer.append(audio=base64.b64encode(data).decode())

    # ---------- звук ----------
    def _start_audio(self):
        import numpy as np
        import sounddevice as sd

        def mic_cb(indata, frames, t, status):
            data = bytes(indata)
            level = float(np.sqrt(np.mean(np.frombuffer(data, np.int16).astype(np.float32) ** 2)))
            hearing.DIAG["mic_level"] = min(1.0, level / 4000)
            if not self.active:
                self._ambient = self._ambient * 0.995 + level * 0.005
                return
            if self.speaking() and config.REALTIME_ECHO_GATE and not self._gate(level):
                self._pre.append(data)
                return
            if self._pre:  # перебивание началось чуть раньше порога — отдаём и начало фразы
                for chunk in self._pre:
                    self._push(chunk)
                self._pre.clear()
            self._push(data)

        def out_cb(outdata, frames, t, status):
            need = frames * 2
            with self.out_lock:
                chunk = bytes(self.out[:need])
                del self.out[:need]
                self.cur_played += len(chunk)
                if chunk:
                    self.playing_until = time.time() + 0.25
            if len(chunk) < need:
                chunk += b"\0" * (need - len(chunk))
            outdata[:] = chunk
            arr = np.frombuffer(chunk, np.int16).astype(np.float32)
            hearing.DIAG["out_level"] = min(1.0, float(np.sqrt(np.mean(arr ** 2))) / 5000)

        self._in = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK, callback=mic_cb)
        self._outs = sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK, callback=out_cb)
        self._in.start()
        self._outs.start()

    def _push(self, data: bytes):
        if self.loop and self._mic_q is not None:
            try:
                self.loop.call_soon_threadsafe(self._mic_q.put_nowait, data)
            except Exception:  # noqa: BLE001 — очередь переполнена: лучше потерять 20 мс, чем отстать
                pass

    def _gate(self, level: float) -> bool:
        """Пока он говорит: пропускаем только вас — звук заметно громче его эха из колонок."""
        now = time.time()
        if now < self._gate_open_until:
            if level > self._ambient * 2:
                self._gate_open_until = now + 0.6
            return True
        echo = sorted(self._echo)[int(len(self._echo) * 0.9)] if len(self._echo) > 20 else 0
        trigger = max(self._ambient * 3, echo * 1.6, 400)
        if level > trigger:
            self._loud += 1
            if self._loud >= 6:  # 120 мс уверенного голоса
                self._gate_open_until = now + 0.6
                hearing.DIAG["barge"] = "перебили голосом"
                return True
        else:
            self._loud = 0
            self._echo.append(level)
        return False

    def _truncate(self):
        with self.out_lock:
            item, played = self.cur_item, self.cur_played
            self.out.clear()
            self.playing_until = 0
        if item:
            self._send({"type": "conversation.item.truncate", "item_id": item, "content_index": 0,
                        "audio_end_ms": played // BYTES_PER_MS})
            self.cur_item = None

    # ---------- события ----------
    async def _on_event(self, ev):
        kind = ev.type
        if kind == "response.output_audio.delta":
            with self.out_lock:
                if ev.item_id != self.cur_item:
                    self.cur_item, self.cur_played = ev.item_id, 0
                self.out.extend(base64.b64decode(ev.delta))
            hearing.DIAG["state"] = "говорю"
            self.last_voice = time.time()
        elif kind == "response.output_audio_transcript.delta":
            self.said += ev.delta
            hearing.DIAG.update(last_said=self.said[-400:], said_at=time.time())
        elif kind == "response.output_audio_transcript.done":
            text = getattr(ev, "transcript", "") or self.said
            self.said = ""
            if text:
                hearing.DIAG.update(last_said=text, said_at=time.time())
                storage.log("jarvis", text)
        elif kind == "input_audio_buffer.speech_started":
            if self.speaking():
                self._truncate()  # перебили — замолкаем мгновенно
            hearing.DIAG["state"] = "слушаю"
            self.last_voice = time.time()
        elif kind == "conversation.item.input_audio_transcription.completed":
            text = (ev.transcript or "").strip()
            if text:
                hearing.DIAG.update(last_text=text, last_at=time.time(), last_engine="живой голос")
                storage.log("user", text)
                activity.emit("voice", text[:200], "", "voice")
            self.last_voice = time.time()
        elif kind == "response.function_call_arguments.done":
            self.pending_calls += 1
            threading.Thread(target=self._call_tool, args=(ev.name, ev.arguments, ev.call_id), daemon=True).start()
        elif kind == "response.done":
            meta = getattr(ev.response, "metadata", None) or {}
            key = meta.get("announce") if isinstance(meta, dict) else None
            if key and key in self._announce_done:
                self._announce_done.pop(key).set()
            if hearing.DIAG.get("state") == "думаю":
                hearing.DIAG["state"] = "слушаю"
        elif kind == "response.created":
            if self.active:
                hearing.DIAG["state"] = "думаю"
        elif kind == "error":
            err = ev.error
            if getattr(err, "code", "") not in ("response_cancel_not_active",):
                self.on_status(f"⚠ Живой голос: {getattr(err, 'message', err)}")

    def _call_tool(self, name: str, arguments: str, call_id: str):
        from .runner import run_tool
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        try:
            if name == "delegate_to_claude":
                out = self._delegate(args.get("task", ""))
            else:
                t = self.tools.get(name)
                confirmed = bool(args.pop("confirmed", False))
                if not t:
                    out = f"Нет инструмента {name}"
                elif t.dangerous and config.CONFIRM_DANGEROUS and not confirmed:
                    out = ("Нужно подтверждение: коротко спроси хозяйку голосом, сделать ли это. Если согласится — "
                           "вызови этот же инструмент снова с теми же параметрами и confirmed=true.")
                else:
                    out, _ = run_tool(t, name, args, lambda *a, **k: True, self.on_status)
        except Exception as e:  # noqa: BLE001
            out = f"Ошибка: {type(e).__name__}: {e}"
        self._send({"type": "conversation.item.create", "item": {
            "type": "function_call_output", "call_id": call_id, "output": str(out)[:6000]}})
        self.pending_calls -= 1
        if self.pending_calls <= 0:
            self.pending_calls = 0
            self._send({"type": "response.create"})
        self.last_voice = time.time()

    def _delegate(self, task: str) -> str:
        """Claude Code в фоне: сразу отвечаем, результат придёт отдельным сообщением."""
        def work():
            from .brain_claude_code import ClaudeCodeBrain
            activity.task_start(f"Claude Code: {task[:180]}", "claude")
            try:
                brain = self.__dict__.get("_claude") or ClaudeCodeBrain(confirm=self.confirm or (lambda *a, **k: False),
                                                                        on_status=self.on_status)
                self._claude = brain
                result = brain.ask(task)
                activity.task_end(result)
            except Exception as e:  # noqa: BLE001
                result = f"не получилось: {e}"
                activity.task_end(result, ok=False)
            from . import notify
            notify.toast("Claude Code закончил", result[:200])
            self.inject(f"Фоновая задача «{task[:120]}» завершена. Итог: {result[:1500]}")
            if not self.active:  # разговор уже «уснул» — даём сказать и снова засыпаем
                self.activate()
        threading.Thread(target=work, daemon=True).start()
        return "Задача передана Claude Code и выполняется в фоне. Скажи хозяйке об этом одной фразой."

    # ---------- сон ----------
    def idle_check(self) -> bool:
        """True — пора «уснуть»: давно тишина, он не говорит и ничего не ждёт."""
        return (self.active and not self.speaking() and self.pending_calls == 0
                and time.time() - self.last_voice > config.REALTIME_IDLE)
