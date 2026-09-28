"""Мозг Джарвиса на OpenAI (GPT) — тот же набор инструментов, что и у версии на Claude."""
import json
from datetime import datetime
from typing import Callable

import openai

from . import config, storage
from .brain import MAX_HISTORY, SYSTEM
from .runner import run_tool
from .tools import load_all
from .tools.info import DAYS
from .tools.tasks import memory_text


class OpenAIBrain:
    def __init__(self, confirm: Callable[[str], bool], on_status: Callable[[str], None] = print):
        self.client = openai.OpenAI()
        self.tools = load_all()
        self.confirm = confirm
        self.on_status = on_status
        self.messages: list = []
        self.tool_schemas = [
            {"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.schema()["input_schema"]}}
            for t in self.tools.values()
        ]

    def reset(self):
        self.messages = []

    def _call(self):
        system = SYSTEM.format(user=config.USER_NAME, memory=memory_text() or "пока ничего")
        return self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}] + self.messages,
            tools=self.tool_schemas,
        )

    def _run_tool(self, name: str, args: dict) -> str:
        t = self.tools.get(name)
        if not t:
            return f"Нет инструмента {name}"
        return run_tool(t, name, args, self.confirm, self.on_status)[0]

    def ask(self, text: str) -> str:
        if len(self.messages) > MAX_HISTORY:
            self.reset()
        n = datetime.now()
        storage.log("user", text)
        self.messages.append({"role": "user",
                              "content": f"[Сейчас {n:%Y-%m-%d %H:%M}, {DAYS[n.weekday()]}]\n{text}"})
        try:
            answer = self._loop()
        except openai.AuthenticationError:
            answer = "Ключ OpenAI не подходит. Проверьте OPENAI_API_KEY в файле точка env."
        except openai.APIConnectionError:
            answer = "Нет связи с сервером. Проверьте интернет."
        except openai.RateLimitError:
            answer = "Лимит OpenAI исчерпан или закончились деньги на балансе."
        except openai.APIStatusError as e:
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
            msg = self._call().choices[0].message
            self.messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return (msg.content or "").strip() or "Готово."
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    out = self._run_tool(call.function.name, args)
                except json.JSONDecodeError:
                    out = "Ошибка: неверные аргументы"
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": out[:10000]})
        return "Задача оказалась слишком длинной, я остановился."
