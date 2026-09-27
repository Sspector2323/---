"""Управление компьютером: питание, программы, звук, окна, клавиатура, терминал."""
import os
import platform
import shutil
import subprocess
import webbrowser
from datetime import datetime

from . import I, S, tool
from ..config import DATA_DIR

OS = platform.system()  # Windows / Darwin / Linux


def _run(cmd, shell=False, timeout=60) -> str:
    r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    return out[-4000:] if out else f"готово (код {r.returncode})"


# ---------- Питание ----------

@tool("shutdown_computer", "Выключить компьютер через указанное число секунд.",
      {"delay_seconds": I("Задержка в секундах, по умолчанию 30")}, dangerous=True)
def shutdown_computer(delay_seconds: int = 30):
    if OS == "Windows":
        return _run(["shutdown", "/s", "/t", str(delay_seconds)])
    return _run(["shutdown", "-h", f"+{max(1, delay_seconds // 60)}"])


@tool("restart_computer", "Перезагрузить компьютер.",
      {"delay_seconds": I("Задержка в секундах, по умолчанию 30")}, dangerous=True)
def restart_computer(delay_seconds: int = 30):
    if OS == "Windows":
        return _run(["shutdown", "/r", "/t", str(delay_seconds)])
    return _run(["shutdown", "-r", f"+{max(1, delay_seconds // 60)}"])


@tool("cancel_shutdown", "Отменить запланированное выключение или перезагрузку.")
def cancel_shutdown():
    return _run(["shutdown", "/a"] if OS == "Windows" else ["shutdown", "-c"])


@tool("sleep_computer", "Перевести компьютер в спящий режим.", dangerous=True)
def sleep_computer():
    if OS == "Windows":
        return _run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
    if OS == "Darwin":
        return _run(["pmset", "sleepnow"])
    return _run(["systemctl", "suspend"])


@tool("lock_computer", "Заблокировать экран.")
def lock_computer():
    if OS == "Windows":
        return _run("rundll32.exe user32.dll,LockWorkStation", shell=True)
    if OS == "Darwin":
        return _run(["pmset", "displaysleepnow"])
    return _run(["loginctl", "lock-session"])


# ---------- Программы и сайты ----------

@tool("open_app", "Открыть программу по названию (например: блокнот, калькулятор, chrome, telegram, spotify, проводник).",
      {"name": S("Название программы")}, ["name"])
def open_app(name: str):
    aliases = {
        "блокнот": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
        "калькулятор": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
        "проводник": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
        "терминал": {"Windows": "cmd", "Darwin": "Terminal", "Linux": "gnome-terminal"},
        "диспетчер задач": {"Windows": "taskmgr", "Darwin": "Activity Monitor", "Linux": "gnome-system-monitor"},
        "настройки": {"Windows": "ms-settings:", "Darwin": "System Settings", "Linux": "gnome-control-center"},
        "браузер": {"Windows": "https://google.com", "Darwin": "Safari", "Linux": "xdg-open https://google.com"},
    }
    target = aliases.get(name.lower().strip(), {}).get(OS, name)
    try:
        if OS == "Windows":
            os.startfile(target) if ":" in target or "." in target else subprocess.Popen(f'start "" "{target}"', shell=True)
        elif OS == "Darwin":
            subprocess.Popen(["open", "-a", target])
        else:
            subprocess.Popen(target, shell=True)
        return f"Открываю {name}"
    except Exception as e:  # noqa: BLE001
        return f"Не получилось открыть {name}: {e}"


@tool("close_app", "Закрыть программу по имени процесса (например chrome, telegram, notepad).",
      {"name": S("Имя процесса")}, ["name"], dangerous=True)
def close_app(name: str):
    import psutil
    killed = []
    for p in psutil.process_iter(["name"]):
        pname = (p.info["name"] or "").lower()
        if name.lower() in pname:
            try:
                p.terminate()
                killed.append(pname)
            except Exception:  # noqa: BLE001
                pass
    return f"Закрыто: {', '.join(sorted(set(killed)))}" if killed else f"Процесс «{name}» не найден"


@tool("open_url", "Открыть сайт или поиск в браузере.",
      {"url": S("Адрес сайта или поисковый запрос")}, ["url"])
def open_url(url: str):
    if " " in url or "." not in url:
        url = "https://www.google.com/search?q=" + url.replace(" ", "+")
    elif not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Открыл {url}"


@tool("play_youtube", "Найти и открыть видео или музыку на YouTube.",
      {"query": S("Что найти")}, ["query"])
def play_youtube(query: str):
    webbrowser.open("https://www.youtube.com/results?search_query=" + query.replace(" ", "+"))
    return f"Ищу на YouTube: {query}"


# ---------- Звук и медиа ----------

def _keys(key: str, times: int = 1):
    import pyautogui
    for _ in range(times):
        pyautogui.press(key)


@tool("volume", "Изменить громкость: up/down/mute, steps — сколько шагов (1 шаг ≈ 2%).",
      {"action": S("up, down или mute", enum=["up", "down", "mute"]), "steps": I("Шагов, по умолчанию 5")},
      ["action"])
def volume(action: str, steps: int = 5):
    if OS == "Darwin":
        if action == "mute":
            return _run(["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"])
        sign = "+" if action == "up" else "-"
        return _run(["osascript", "-e", f"set volume output volume (output volume of (get volume settings) {sign} {steps * 2})"])
    if OS == "Linux":
        arg = "toggle" if action == "mute" else f"{steps * 2}%{'+' if action == 'up' else '-'}"
        return _run(["amixer", "-D", "pulse", "sset", "Master", arg])
    _keys({"up": "volumeup", "down": "volumedown", "mute": "volumemute"}[action], 1 if action == "mute" else steps)
    return "Громкость изменена"


@tool("media_control", "Управление музыкой/видео: play_pause, next, previous.",
      {"action": S("play_pause, next или previous", enum=["play_pause", "next", "previous"])}, ["action"])
def media_control(action: str):
    _keys({"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack"}[action])
    return "Готово"


# ---------- Клавиатура, экран, буфер ----------

@tool("type_text", "Напечатать текст в активное окно (как будто с клавиатуры).",
      {"text": S("Текст")}, ["text"])
def type_text(text: str):
    import pyautogui
    import pyperclip
    pyperclip.copy(text)  # через буфер — чтобы работала кириллица
    pyautogui.hotkey("command" if OS == "Darwin" else "ctrl", "v")
    return "Напечатал"


@tool("press_hotkey", "Нажать сочетание клавиш, например 'ctrl+c', 'alt+tab', 'win+d', 'enter'.",
      {"keys": S("Клавиши через +")}, ["keys"])
def press_hotkey(keys: str):
    import pyautogui
    pyautogui.hotkey(*[k.strip().lower() for k in keys.split("+")])
    return f"Нажал {keys}"


@tool("clipboard", "Прочитать содержимое буфера обмена или записать в него текст.",
      {"text": S("Если указан — записать этот текст в буфер")})
def clipboard(text: str | None = None):
    import pyperclip
    if text:
        pyperclip.copy(text)
        return "Скопировал в буфер"
    return pyperclip.paste()[:4000] or "Буфер пуст"


@tool("screenshot", "Сделать скриншот экрана и сохранить в папку data/screenshots.")
def screenshot():
    import pyautogui
    folder = DATA_DIR / "screenshots"
    folder.mkdir(exist_ok=True)
    path = folder / f"screen_{datetime.now():%Y%m%d_%H%M%S}.png"
    pyautogui.screenshot(str(path))
    return f"Скриншот сохранён: {path}"


# ---------- Состояние системы ----------

@tool("system_status", "Загрузка процессора, памяти, диска, заряд батареи, время работы.")
def system_status():
    import psutil
    disk_root = "C:\\" if OS == "Windows" else "/"
    parts = [
        f"Процессор: {psutil.cpu_percent(interval=0.5)}%",
        f"Память: {psutil.virtual_memory().percent}%",
        f"Диск: {psutil.disk_usage(disk_root).percent}% занято",
    ]
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat:
        parts.append(f"Батарея: {bat.percent:.0f}%{' (заряжается)' if bat.power_plugged else ''}")
    up = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    parts.append(f"Работает: {up.days} д {up.seconds // 3600} ч {up.seconds % 3600 // 60} мин")
    return "; ".join(parts)


@tool("top_processes", "Показать самые прожорливые процессы.")
def top_processes():
    import psutil
    procs = sorted(psutil.process_iter(["name", "memory_percent"]),
                   key=lambda p: p.info["memory_percent"] or 0, reverse=True)[:8]
    return "\n".join(f"{p.info['name']}: {p.info['memory_percent']:.1f}% памяти" for p in procs)


# ---------- Терминал ----------

@tool("run_command",
      "Выполнить команду в терминале компьютера (cmd/PowerShell на Windows, bash на Mac/Linux) и вернуть вывод. "
      "Используй для всего, для чего нет отдельного инструмента.",
      {"command": S("Команда")}, ["command"], dangerous=True)
def run_command(command: str):
    if OS == "Windows" and shutil.which("powershell"):
        return _run(["powershell", "-NoProfile", "-Command", command], timeout=120)
    return _run(command, shell=True, timeout=120)


@tool("open_dashboard", "Открыть дашборд Джарвиса в браузере (задачи, напоминания, почта, заметки, состояние ПК).")
def open_dashboard():
    from ..config import DASHBOARD_PORT
    webbrowser.open(f"http://localhost:{DASHBOARD_PORT}")
    return "Дашборд открыт"
