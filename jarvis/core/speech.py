"""Текст «для уха»: вслух — только суть. Ссылки, пути к файлам, код и разметка остаются на экране."""
import re

URL = re.compile(r"(https?://|www\.)\S+", re.I)
MD_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s,;«»\"')]+")
UNIX_PATH = re.compile(r"(?<![\w/])(?:~|/)(?:[\w.\-]+/)+[\w.\-]+")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
CODE_BLOCK = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`([^`]{0,40})`|`[^`]*`")
LONG_ID = re.compile(r"\b(?=[\w-]*\d)[\w-]{24,}\b")  # uid, хэши, id страниц
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")


def for_speech(text: str) -> str:
    t = CODE_BLOCK.sub(" (код — на экране) ", text)
    t = MD_LINK.sub(r"\1", t)                      # [название](ссылка) → название
    had_link = bool(URL.search(t))
    t = URL.sub("", t)
    t = WIN_PATH.sub("файл", t)
    t = UNIX_PATH.sub("файл", t)
    t = LONG_ID.sub("", t)
    t = INLINE_CODE.sub(lambda m: m.group(1) or "", t)
    t = EMOJI.sub("", t)
    t = re.sub(r"[*_#>|]+", " ", t)                # markdown-звёздочки, решётки, таблицы
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)  # маркеры списков
    t = re.sub(r"\(\s*\)|\[\s*\]", "", t)
    t = re.sub(r"\s+([,.:;!?])", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n\s*", ". ", t).strip(" .;:,")
    t = re.sub(r"(\.\s*){2,}", ". ", t)
    t = re.sub(r"([:;,!?])\.\s", r"\1 ", t)
    if had_link and "экран" not in t:
        t += ". Ссылка — на экране."
    return t.strip()
