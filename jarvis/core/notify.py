"""Уведомления Windows (всплывают в углу экрана и остаются в Центре уведомлений).

Джарвис пишет сюда то, что важно и когда вы не смотрите на его окна: напоминания, готовые фоновые задачи,
новые задачи из рабочих чатов. Клик по уведомлению открывает дашборд.
"""
import os

from . import config


def _icon():
    from .icon import icon_path
    return icon_path()


def toast(title: str, text: str = "", open_url: str = ""):
    if not config.NOTIFICATIONS:
        return False
    if os.name == "nt":
        try:
            from winotify import Notification, audio
            n = Notification(app_id="J.A.R.V.I.S.", title=title[:120], msg=(text or "")[:250],
                             icon=str(_icon()),
                             launch=open_url or f"http://localhost:{config.DASHBOARD_PORT}/core")
            n.set_audio(audio.Silent, loop=False)  # звук у Джарвиса свой
            n.show()
            return True
        except Exception:  # noqa: BLE001
            pass
    print(f"🔔 {title}: {text}")
    return False
