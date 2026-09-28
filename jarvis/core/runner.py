"""Выполнение одного инструмента Джарвиса — с подтверждением и записью в «Прямой эфир»."""
import json
import time
from typing import Callable

from . import activity, config


def run_tool(tool, name: str, args: dict, confirm: Callable, on_status: Callable) -> tuple[str, bool]:
    label, detail = activity.describe(name, args)
    if tool.dangerous and config.CONFIRM_DANGEROUS:
        full = f"{label}: {detail}" if detail else label
        # вслух — только короткая фраза; подробности — в окне на дашборде и в Телеграме
        if not confirm(full, f"Разрешите {activity.spoken(name)}?"):
            activity.emit("error", f"Отменено: {label}", detail)
            return "Пользователь отменил действие.", False
    activity.emit("tool", label, detail or json.dumps(args, ensure_ascii=False)[:300])
    activity.task_step()
    on_status(f"⚙ {name} {json.dumps(args, ensure_ascii=False)[:200]}")
    t0 = time.time()
    try:
        out = str(tool.func(**args))
        activity.emit("done", f"{label} — готово за {time.time() - t0:.1f} с", out[:800])
        return out, False
    except Exception as e:  # noqa: BLE001
        activity.emit("error", f"{label} — ошибка", f"{type(e).__name__}: {e}")
        return f"Ошибка: {type(e).__name__}: {e}", True
