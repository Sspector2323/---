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
from core.quick import try_quick
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


def reminder_loop(io):
    while True:
        for r in due_reminders():
            io.say(f"{config.USER_NAME}, напоминаю: {r['text']}")
        time.sleep(15)


def main():
    text_mode = "--text" in sys.argv
    key = "OPENAI_API_KEY" if config.AI_PROVIDER == "openai" else "ANTHROPIC_API_KEY"
    if not os.getenv(key):
        print(f"❌ Не найден {key}. Откройте файл .env и вставьте ключ.")
        sys.exit(1)

    if text_mode:
        from core.voice import TextIO
        io = TextIO()
    else:
        from core.voice import Voice
        print("🎙 Настраиваю микрофон…")
        io = Voice()

    if config.AI_PROVIDER == "openai":
        from core.brain_openai import OpenAIBrain as Brain
    else:
        from core.brain import Brain
    brain = Brain(confirm=io.confirm, on_status=lambda s: print("  " + s))
    lock = threading.Lock()

    def ask(text: str) -> str:
        with lock:
            return brain.ask(text)

    url = dashboard.start(ask)
    threading.Thread(target=reminder_loop, args=(io,), daemon=True).start()
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)

    print(f"📊 Дашборд: {url}")
    wake = config.WAKE_WORDS[0].capitalize()
    io.say(f"Джарвис на связи, {config.USER_NAME}." + ("" if text_mode else f" Скажите «{wake}» и команду."))

    follow_up_until = 0.0  # несколько секунд после ответа можно говорить без слова «Джарвис»
    while True:
        heard = io.listen(timeout=None if text_mode else 5, phrase_limit=15)
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
                command = io.listen(timeout=8, phrase_limit=20)
                if not command:
                    continue
                print(f"🎤 Вы: {command}")

        low = command.lower()
        if any(w in low for w in STOP_WORDS):
            io.say(f"Отключаюсь. Хорошего дня, {config.USER_NAME}.")
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
        if answer is None:
            answer = ask(command)
            print(f"  ⏱ мозг думал {time.time() - t0:.1f} с")
        if answer:
            t1 = time.time()
            io.say(answer)
            print(f"  ⏱ голос {time.time() - t1:.1f} с")
        follow_up_until = time.time() + 8


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПока!")
