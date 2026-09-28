"""J.A.R.V.I.S. — голосовой ИИ-ассистент.

Запуск:
    python main.py           — голосовой режим (скажите «Джарвис, ...»)
    python main.py --text    — текстовый режим (без микрофона)
"""
import os
import re
import sys
import threading
import time
import webbrowser

from core import config, dashboard
from core import fillers
from core.quick import is_quick, try_quick
from core.tools.tasks import due_reminders

STOP_WORDS = ("выключись", "отключись", "завершить работу", "пока джарвис", "выход")
RESET_WORDS = ("новый диалог", "забудь разговор", "начни сначала")


def strip_wake(text: str) -> str | None:
    """Если фраза обращена к Джарвису — вернуть команду без имени, иначе None."""
    low = text.lower()
    for w in config.WAKE_WORDS:
        if w in low:
            return re.sub(rf"\b{re.escape(w)}\b[,!.]?", "", text, flags=re.I).strip(" ,.!")
    return None


def hear_rest(io, text: str, text_mode: bool) -> str:
    """Вы сделали паузу — Джарвис ещё секунду слушает и приклеивает продолжение к той же команде."""
    if text_mode:
        return text
    for _ in range(4):
        more = io.listen(timeout=1.0, phrase_limit=45)
        if not more:
            break
        print(f"🎤 …{more}")
        text = f"{text} {more}"
    return text


SHUT_UP = ("стоп", "хватит", "замолчи", "тихо", "стой", "подожди", "отмена", "всё", "не надо")


def ask_with_fillers(io, ask, command: str, cancel=None) -> tuple[str | None, str | None]:
    """Пока мозг думает, Джарвис не молчит. Если его перебили — задача отменяется,
    возвращается (None, что сказали), и сказанное становится новой командой."""
    box = {}
    worker = threading.Thread(target=lambda: box.update(answer=ask(command)), daemon=True)
    worker.start()
    worker.join(1.0)  # быстрые ответы — без перебивок
    waits = fillers.waiting(config.USER_NAME)
    phrase = fillers.first(command, config.USER_NAME)
    while worker.is_alive():
        if not io.confirming:
            io.say(phrase, cache=True, quiet=True)
            if io.barge_text is not None:  # перебили во время «секунду…» — бросаем старую задачу
                if cancel:
                    cancel()
                return None, io.barge_text
        worker.join(7.0)
        phrase = next(waits)
    return box.get("answer", "Готово."), None


def reminder_loop(io):
    while True:
        for r in due_reminders():
            text = f"{config.USER_NAME}, напоминаю: {r['text']}"
            try:  # напоминание дублируется в Телеграм — вдруг вы не у компьютера
                from core.telegram_bot import send
                send("⏰ " + text)
            except Exception:  # noqa: BLE001
                pass
            io.say(text)
        time.sleep(15)


def main():
    text_mode = "--text" in sys.argv
    key = {"openai": "OPENAI_API_KEY", "hybrid": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(config.AI_PROVIDER)
    if key and not os.getenv(key):
        print(f"❌ Не найден {key}. Откройте файл .env и вставьте ключ.")
        sys.exit(1)

    # Дашборд и анимация стартуют первыми — пока идёт анимация, настраиваются микрофон и мозг
    t_start = time.time()
    url = dashboard.start()
    from core import intro
    intro_on = config.INTRO_ANIMATION and "--no-intro" not in sys.argv
    want_dash = "--no-browser" not in sys.argv and config.DASHBOARD_SCREENS != "off"
    how = intro.launch(url, with_dashboards=want_dash) if intro_on else None
    if not intro_on and want_dash and intro.launch_native(url, "dash"):
        how = "native"
    intro_on = bool(how) and intro_on
    brief_box = {}
    if config.MORNING_BRIEF:
        from core.briefing import brief
        threading.Thread(target=lambda: brief_box.update(text=brief()), daemon=True).start()

    if text_mode:
        from core.voice import TextIO
        io = TextIO()
    else:
        from core.voice import Voice
        print("🎙 Настраиваю микрофон…")
        io = Voice()

    from core.confirmer import Confirmer
    confirmer = Confirmer(io, voice_enabled=not text_mode)

    if config.AI_PROVIDER == "claude_code":
        from core.brain_claude_code import ClaudeCodeBrain as Brain
    elif config.AI_PROVIDER in ("openai", "hybrid"):
        from core.brain_openai import OpenAIBrain as Brain
    else:
        from core.brain import Brain
    try:
        brain = Brain(confirm=confirmer.ask, on_status=lambda s: print("  " + s))
    except RuntimeError as e:
        print(f"❌ {e}")
        if config.AI_PROVIDER == "claude_code" and os.getenv("OPENAI_API_KEY"):
            print("↪ Пока работаю на мозге OpenAI. Проверьте Claude Code: в НОВОМ окне PowerShell — claude --version")
            from core.brain_openai import OpenAIBrain
            brain = OpenAIBrain(confirm=confirmer.ask, on_status=lambda s: print("  " + s))
        else:
            print("  Проверьте в НОВОМ окне PowerShell: claude --version. Если версия показывается — "
                  "впишите путь из команды  where.exe claude  в ⚙ Настройки → CLAUDE_PATH.")
            input("Нажмите Enter для выхода…")
            sys.exit(1)
    lock = threading.Lock()

    def ask(text: str) -> str:
        from core import activity
        source = "telegram" if text.startswith("[Сообщение из Телеграма]") else "voice"
        with lock:
            activity.task_start(text.replace("[Сообщение из Телеграма] ", "✈️ ")[:200], source)
            try:
                answer = brain.ask(text)
            except Exception as e:  # noqa: BLE001
                activity.task_end(f"Ошибка: {e}", ok=False)
                raise
            activity.task_end(answer)
            return answer

    dashboard.BRAIN.update(ask=ask, confirm=confirmer.ask, say=io.say, confirmer=confirmer)
    from core.telegram_bot import Bot
    Bot(ask, confirmer).start()  # личный Телеграм-бот (если задан TELEGRAM_BOT_TOKEN)
    from core import tg_reader
    threading.Thread(target=tg_reader.background_loop, daemon=True).start()  # задачи из рабочих чатов
    threading.Thread(target=reminder_loop, args=(io,), daemon=True).start()
    print(f"📊 Дашборд: {url}")

    if intro_on:  # приветствие звучит, когда на экране появляется надпись
        time.sleep(max(0.0, 3.6 - (time.time() - t_start)))
    io.say(config.GREETING.format(user=config.USER_NAME))
    if config.MORNING_BRIEF:
        for _ in range(40):  # сводка собирается параллельно; ждём не дольше 4 секунд
            if "text" in brief_box:
                break
            time.sleep(0.1)
        if brief_box.get("text"):
            io.say(brief_box["text"])
            if config.TELEGRAM_BRIEF:
                try:
                    from core.telegram_bot import send
                    send(f"☀️ {config.GREETING.format(user=config.USER_NAME)}\n\n{brief_box['text']}")
                except Exception:  # noqa: BLE001
                    pass
    # фразы-перебивки озвучиваем заранее, в фоне — потом они звучат без задержки
    threading.Thread(target=io.prewarm, args=([p.format(user=config.USER_NAME) for p in fillers.ALL],),
                     daemon=True).start()
    if want_dash and how != "native":  # окна Windows открывают дашборды сами; иначе — в браузере после анимации
        threading.Timer(max(0.0, 9.5 - (time.time() - t_start)), webbrowser.open, [url]).start()

    follow_up_until = 0.0  # несколько секунд после ответа можно говорить без слова «Джарвис»
    pending = None  # то, что вы сказали, перебив Джарвиса — выполняется следующей командой
    while True:
        if pending is not None:
            heard, pending = pending, None
            follow_up_until = time.time() + 1  # после перебивания «Джарвис» говорить не нужно
        else:
            heard = io.listen(timeout=None if text_mode else 5, phrase_limit=45)
        if not heard:
            continue
        print(f"🎤 Вы: {heard}" + ("" if text_mode else f"   (⏱ распознал за {io.last_stt:.1f} с)"))

        if text_mode or time.time() < follow_up_until:
            command = strip_wake(heard) or heard
        else:
            command = strip_wake(heard)
            if command is None:
                continue  # говорили не с Джарвисом
            if not command:
                io.beep()  # «слушаю» — сигналом, это мгновенно
                command = io.listen(timeout=8, phrase_limit=45)
                if not command:
                    continue
                print(f"🎤 Вы: {command}")

        if not is_quick(command):  # простые команды («громче») выполняем сразу, остальное — дослушиваем
            command = hear_rest(io, command, text_mode)
        low = command.lower()
        if any(w in low for w in STOP_WORDS):
            io.say(f"Всегда к вашим услугам, {config.USER_NAME}. Отключаюсь.")
            break
        if any(w in low for w in RESET_WORDS):
            brain.reset()
            io.say("Начнём с чистого листа.")
            continue
        if low in ("стоп", "хватит", "тихо", "отмена"):
            follow_up_until = 0
            continue

        t0 = time.time()
        answer = try_quick(command)
        if answer is not None:
            from core import activity
            activity.emit("done", f"Быстрая команда: {command}", answer or "")
        barged = None
        if answer is None:
            answer, barged = ask_with_fillers(io, ask, command, cancel=getattr(brain, "cancel", None))
            print(f"  ⏱ мозг думал {time.time() - t0:.1f} с")
        if answer and barged is None:
            t1 = time.time()
            io.say(answer)
            print(f"  ⏱ голос {time.time() - t1:.1f} с")
            barged = io.barge_text
        follow_up_until = time.time() + 8
        if barged is not None:  # вы перебили: замолкаем; если сказали новое — сразу выполняем
            from core import activity
            clean = barged.strip().lower().strip(".!,")
            activity.emit("voice", "Вы перебили Джарвиса", barged or "(неразборчиво)")
            if clean and clean not in SHUT_UP:
                pending = barged


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПока!")
