"""Одна копия Джарвиса: при запуске закрываем старую (автозапуск, забытое свёрнутое окно),
иначе новый Джарвис не может занять адрес дашборда и вы видите старый."""
import os

from . import config


def kill_old_instances() -> list[str]:
    try:
        import psutil
    except ImportError:
        return []
    me = os.getpid()
    killed = []
    # 1) кто держит порт дашборда
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.laddr and c.laddr.port == config.DASHBOARD_PORT and c.status == psutil.CONN_LISTEN and c.pid and c.pid != me:
                killed += _kill(psutil.Process(c.pid))
    except (psutil.AccessDenied, PermissionError):
        pass
    # 2) другие python с main.py этой папки и окна screens
    root = str(config.ROOT).lower()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == me or "python" not in (p.info["name"] or "").lower():
                continue
            cmd = " ".join(p.info["cmdline"] or []).lower()
            if ("main.py" in cmd and (root in cmd or "jarvis" in cmd)) or "core.screens" in cmd:
                killed += _kill(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def _kill(proc) -> list[str]:
    import psutil
    try:
        if "python" not in proc.name().lower():
            return []
        for ch in proc.children(recursive=True):
            ch.kill()
        proc.kill()
        proc.wait(5)
        return [f"PID {proc.pid}"]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        return []
