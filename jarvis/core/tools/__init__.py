"""Реестр инструментов Джарвиса.

Каждый инструмент — обычная функция, помеченная декоратором @tool.
Из описания автоматически собирается JSON-схема для Claude.
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    properties: dict = field(default_factory=dict)
    required: list = field(default_factory=list)
    dangerous: bool = False  # требует голосового подтверждения

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
            },
        }


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict | None = None,
         required: list | None = None, dangerous: bool = False):
    def wrap(func: Callable) -> Callable:
        REGISTRY[name] = Tool(name, description, func, properties or {}, required or [], dangerous)
        return func
    return wrap


def S(desc: str, **extra) -> dict:
    return {"type": "string", "description": desc, **extra}


def I(desc: str, **extra) -> dict:
    return {"type": "integer", "description": desc, **extra}


def load_all() -> dict[str, Tool]:
    # Импорт модулей регистрирует их инструменты
    from . import system, files, tasks, mail, info, claude_code, notion, github, workspace  # noqa: F401
    return REGISTRY
