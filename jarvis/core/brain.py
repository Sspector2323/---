"""Мозг Джарвиса: Claude + цикл вызова инструментов."""
import json
from datetime import datetime
from typing import Callable

import anthropic

from . import config, storage
from .tools import load_all
from .tools.info import DAYS
from .tools.tasks import memory_text

SYSTEM = """Ты — Джарвис, личный голосовой ИИ-ассистент в стиле J.A.R.V.I.S. из «Железного человека».
Ты живёшь на компьютере пользователя и управляешь им через инструменты. Обращайся к пользователю «{user}».

Как отвечать:
- Твои ответы озвучиваются голосом. Говори коротко (1–3 предложения), по-русски, без markdown, списков,
  эмодзи и ссылок. Числа и время пиши так, как их удобно произнести.
- Если нужно действие — сразу вызывай инструмент, не спрашивай разрешения (опасные действия подтверждаются
  автоматически). После действия коротко скажи, что сделано.
- Для многошаговых задач вызывай несколько инструментов подряд. Если для чего-то нет отдельного
  инструмента — используй run_command, а для больших задач (код, сайты, разбор проектов) — claude_code.
- Письма пересказывай своими словами: кто, о чём, что требуется. Не зачитывай целиком.
- Относительные даты («завтра в 9», «через час») переводи в формат ГГГГ-ММ-ДД ЧЧ:ММ по текущему времени.
- Если узнал о пользователе что-то важное и долгосрочное — сохрани через remember.
- Рабочие проекты живут в Notion («Сводка задач»: notion_tasks/notion_add_task) и на GitHub (github_overview).
  «Мои задачи» по работе — это Notion, личные мелочи — add_task. Итоги важных дел записывай в штаб: notion_log.
- Ветки claude/… в репозиториях — это работа Claude в облаке; рассказывай о ней, если спрашивают, что он делает.
- Лёгкая британская ирония допустима, но польза важнее.

Что ты помнишь о пользователе:
{memory}"""

MAX_HISTORY = 60


class Brain:
    def __init__(self, confirm: Callable[[str], bool], on_status: Callable[[str], None] = print):
        self.client = anthropic.Anthropic()
        self.tools = load_all()
        self.confirm = confirm
        self.on_status = on_status
        self.messages: list = []
        self.tool_schemas = [t.schema() for t in self.tools.values()] + [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
        ]

    def reset(self):
        self.messages = []

    def _system(self) -> str:
        return SYSTEM.format(user=config.USER_NAME, memory=memory_text() or "пока ничего")

    def _call(self):
        return self.client.beta.messages.create(
            model=config.MODEL,
            max_tokens=16000,
            system=self._system(),
            tools=self.tool_schemas,
            messages=self.messages,
            output_config={"effort": config.EFFORT},
            cache_control={"type": "ephemeral"},
            # если основная модель откажется — запрос сам перейдёт на запасную
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        t = self.tools.get(name)
        if not t:
            return f"Нет инструмента {name}", True
        if t.dangerous and config.CONFIRM_DANGEROUS:
            details = ", ".join(f"{k}: {v}" for k, v in args.items())
            if not self.confirm(f"{t.description} {details}".strip()):
                return "Пользователь отменил действие.", False
        self.on_status(f"⚙ {name} {json.dumps(args, ensure_ascii=False)[:200]}")
        try:
            return str(t.func(**args)), False
        except Exception as e:  # noqa: BLE001
            return f"Ошибка: {type(e).__name__}: {e}", True

    def ask(self, text: str) -> str:
        if len(self.messages) > MAX_HISTORY:
            self.reset()
        n = datetime.now()
        storage.log("user", text)
        self.messages.append({"role": "user",
                              "content": f"[Сейчас {n:%Y-%m-%d %H:%M}, {DAYS[n.weekday()]}]\n{text}"})
        try:
            answer = self._loop()
        except anthropic.AuthenticationError:
            answer = "Ключ Claude не подходит. Проверьте ANTHROPIC_API_KEY в файле точка env."
        except anthropic.APIConnectionError:
            answer = "Нет связи с сервером. Проверьте интернет."
        except anthropic.RateLimitError:
            answer = "Слишком много запросов, подождите немного."
        except anthropic.APIStatusError as e:
            answer = f"Ошибка сервера {e.status_code}."
        except Exception as e:  # noqa: BLE001 — голосовой цикл не должен падать
            answer = f"Что-то пошло не так: {e}"
        else:
            storage.log("jarvis", answer)
            return answer
        self.reset()  # после сбоя начинаем диалог заново, чтобы история не сломалась
        storage.log("jarvis", answer)
        return answer

    def _loop(self) -> str:
        for _ in range(25):
            resp = self._call()
            self.messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "refusal":
                self.reset()
                return "Боюсь, с этим я помочь не могу."
            if resp.stop_reason == "pause_turn":
                continue
            calls = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not calls:
                return " ".join(b.text for b in resp.content if b.type == "text").strip() or "Готово."
            results = []
            for c in calls:
                out, is_err = self._run_tool(c.name, c.input or {})
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": out[:10000],
                                "is_error": is_err})
            self.messages.append({"role": "user", "content": results})
        return "Задача оказалась слишком длинной, я остановился."
