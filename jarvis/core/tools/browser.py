"""Руки Джарвиса в браузере: открыть сайт, прочитать страницу, нажать, заполнить поле, посмотреть.

Идея из adewaskar/jarvis (MIT). Здесь — через Playwright и обычный Edge (или Chrome) на вашем компьютере,
в отдельном профиле «Джарвис» (data/browser_profile). Войдите в нужные сайты один раз в этом окне —
дальше Джарвис работает там уже с вашими входами. Основной профиль Chrome новые версии браузера
автоматизировать не разрешают, поэтому профиль свой.

Браузер живёт в главном процессе Джарвиса и в одном своём потоке (так требует Playwright); инструменты,
вызванные из Claude Code, приходят сюда через /api/exec.
"""
import queue
import re
import threading
import time
from datetime import datetime

from .. import activity, config
from . import I, S, tool

_q: "queue.Queue" = queue.Queue()
_thread = None
_state = {"pw": None, "ctx": None, "page": None}

MARK_JS = """
() => {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [role=tab],'
            + '[role=menuitem], [contenteditable=true], summary';
  const out = [];
  let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width < 4 || r.height < 4 || st.visibility === 'hidden' || st.display === 'none') continue;
    if (r.bottom < 0 || r.top > innerHeight * 2.5) continue;
    i += 1;
    el.setAttribute('data-jv', i);
    const tag = el.tagName.toLowerCase();
    const kind = tag === 'a' ? 'ссылка' : (tag === 'input' || tag === 'textarea' || el.isContentEditable) ? 'поле'
               : tag === 'select' ? 'список' : 'кнопка';
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || el.title
                   || el.getAttribute('name') || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
    out.push(`${i}. [${kind}] ${label}`);
    if (out.length >= 80) break;
  }
  return out.join('\\n');
}
"""

READ_JS = """
() => {
  const pick = document.querySelector('article') || document.querySelector('main') || document.body;
  const clone = pick.cloneNode(true);
  clone.querySelectorAll('script,style,noscript,nav,footer,aside,iframe,svg,form').forEach(n => n.remove());
  // innerText считает переносы только у элемента на странице — кладём копию за край экрана
  const box = document.createElement('div');
  box.style.cssText = 'position:absolute;left:-99999px;top:0;width:900px';
  box.appendChild(clone);
  document.body.appendChild(box);
  const text = box.innerText || '';
  box.remove();
  return text.replace(/\\n{3,}/g, '\\n\\n').trim();
}
"""


def _worker():
    while True:
        fn, box, done = _q.get()
        try:
            box["result"] = fn()
        except Exception as e:  # noqa: BLE001
            box["error"] = e
        finally:
            done.set()


def _call(fn, timeout: float = 120):
    """Выполнить действие в потоке браузера и дождаться результата."""
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_worker, daemon=True, name="jarvis-browser")
        _thread.start()
    box, done = {}, threading.Event()
    _q.put((fn, box, done))
    if not done.wait(timeout):
        raise TimeoutError("браузер не ответил вовремя")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _page():
    """Текущая вкладка; при первом вызове запускает браузер в профиле Джарвиса."""
    ctx = _state["ctx"]
    if ctx is not None:
        try:
            pages = [p for p in ctx.pages if not p.is_closed()]
            if pages:
                if _state["page"] not in pages:
                    _state["page"] = pages[-1]
                return _state["page"]
        except Exception:  # noqa: BLE001 — окно закрыли руками: запускаем заново
            pass
        try:
            ctx.close()
        except Exception:  # noqa: BLE001
            pass
        _state["ctx"] = None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("нужен пакет playwright: обновите Джарвиса (update_jarvis.bat)") from e
    if _state["pw"] is None:
        _state["pw"] = sync_playwright().start()
    profile = config.DATA_DIR / "browser_profile"
    profile.mkdir(exist_ok=True)
    errors = []
    options = [{"executable_path": config.BROWSER_PATH}] if config.BROWSER_PATH else []
    options += [{"channel": c} for c in dict.fromkeys([config.BROWSER_CHANNEL, "msedge", "chrome"])]
    for opt in options:
        try:
            ctx = _state["pw"].chromium.launch_persistent_context(
                str(profile), headless=config.BROWSER_HEADLESS, no_viewport=True,
                args=["--start-maximized", "--no-first-run", "--no-default-browser-check"], **opt)
            break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{list(opt.values())[0]}: {str(e).splitlines()[0][:120]}")
    else:
        raise RuntimeError("не удалось открыть Edge или Chrome — " + "; ".join(errors))
    _state["ctx"] = ctx
    _state["page"] = ctx.pages[0] if ctx.pages else ctx.new_page()
    ctx.on("page", lambda p: _state.update(page=p))  # новая вкладка (target=_blank) — работаем в ней
    activity.emit("tool", "Браузер Джарвиса открыт", "профиль data/browser_profile")
    return _state["page"]


def _summary(page, chars: int = 1500) -> str:
    try:
        text = page.evaluate(READ_JS)
    except Exception:  # noqa: BLE001
        text = ""
    return f"Открыто: {page.title()} — {page.url}\n\n{text[:chars]}"


def _settle(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:  # noqa: BLE001
        pass


@tool("browser_open",
      "Открыть сайт в браузере Джарвиса (Edge с вашими входами) или найти что-то в интернете. Возвращает заголовок "
      "и начало текста страницы. Дальше: browser_elements → browser_click/browser_type, browser_read, browser_look.",
      {"url": S("Адрес сайта или поисковый запрос"), "new_tab": {"type": "boolean", "description": "В новой вкладке"}},
      ["url"], in_main=True)
def browser_open(url: str, new_tab: bool = False):
    target = url.strip()
    if not re.match(r"^[a-z]+://", target):
        target = f"https://{target}" if re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", target, re.I) else \
            "https://www.google.com/search?q=" + __import__("urllib.parse").parse.quote(target)

    def go():
        page = _page()
        if new_tab:
            page = _state["ctx"].new_page()
            _state["page"] = page
        page.goto(target, wait_until="domcontentloaded", timeout=45000)
        _settle(page)
        page.bring_to_front()
        return _summary(page)
    return _call(go)


@tool("browser_elements",
      "Список кнопок, ссылок и полей на текущей странице браузера с номерами — чтобы потом нажать "
      "browser_click(number=…) или заполнить browser_type(number=…).", {}, [], in_main=True)
def browser_elements():
    def go():
        page = _page()
        return f"{page.title()} — {page.url}\n" + (page.evaluate(MARK_JS) or "Ничего кликабельного не видно.")
    return _call(go)


@tool("browser_click",
      "Нажать на кнопку или ссылку в браузере: по номеру из browser_elements или по видимому тексту. Перед "
      "оплатой, отправкой писем и сообщений, удалением — спроси пользователя.",
      {"number": I("Номер элемента из browser_elements"), "text": S("Видимый текст кнопки или ссылки")},
      [], dangerous=True, in_main=True)
def browser_click(number: int = 0, text: str = ""):
    def go():
        page = _page()
        if number:
            loc = page.locator(f"[data-jv='{int(number)}']")
            if not loc.count():  # страница перерисовалась — разметим заново
                page.evaluate(MARK_JS)
                loc = page.locator(f"[data-jv='{int(number)}']")
        elif text:
            loc = page.get_by_role("button", name=text)
            if not loc.count():
                loc = page.get_by_role("link", name=text)
            if not loc.count():
                loc = page.get_by_text(text, exact=False)
        else:
            return "Скажи, что нажать: номер или текст."
        if not loc.count():
            return "Не нашёл такой элемент — обнови список через browser_elements."
        loc.first.scroll_into_view_if_needed(timeout=5000)
        loc.first.click(timeout=10000)
        _settle(page)
        return "Нажато. " + _summary(page, 800)
    return _call(go)


@tool("browser_type",
      "Ввести текст в поле на странице браузера: по номеру из browser_elements или по подписи/подсказке поля. "
      "submit=true — нажать Enter после ввода.",
      {"text": S("Что ввести"), "number": I("Номер поля из browser_elements"),
       "field": S("Подпись или подсказка поля"), "submit": {"type": "boolean", "description": "Нажать Enter"}},
      ["text"], dangerous=True, in_main=True)
def browser_type(text: str, number: int = 0, field: str = "", submit: bool = False):
    def go():
        page = _page()
        if number:
            loc = page.locator(f"[data-jv='{int(number)}']")
        elif field:
            loc = page.get_by_label(field)
            if not loc.count():
                loc = page.get_by_placeholder(field)
        else:
            loc = page.locator("input:focus, textarea:focus, [contenteditable=true]:focus")
        if not loc.count():
            return "Не нашёл поле — посмотри browser_elements."
        loc.first.fill(text, timeout=10000)
        if submit:
            loc.first.press("Enter")
            _settle(page)
        return "Введено." + (" " + _summary(page, 600) if submit else "")
    return _call(go)


@tool("browser_read",
      "Прочитать текст текущей страницы браузера (статья, письмо, документация). show=true — ещё и вывести "
      "его на экран Джарвиса в режиме чтения.",
      {"show": {"type": "boolean", "description": "Показать на экране Джарвиса"}}, [], in_main=True)
def browser_read(show: bool = False):
    def go():
        page = _page()
        return page.title(), page.url, page.evaluate(READ_JS)
    title, url, text = _call(go)
    if show:
        from .screen import show as show_panel
        paras = "\n\n".join(p.strip() for p in text.split("\n") if p.strip())
        show_panel(title or "Страница", paras[:20000], link=url, size="wide", panel_id="reader")
    return f"{title} — {url}\n\n{text[:12000]}"


@tool("browser_scroll", "Прокрутить страницу браузера вниз или вверх.",
      {"direction": S("down или up", enum=["down", "up"])}, [], in_main=True)
def browser_scroll(direction: str = "down"):
    def go():
        page = _page()
        page.mouse.wheel(0, 900 if direction != "up" else -900)
        time.sleep(0.4)
        return "Прокручено."
    return _call(go)


@tool("browser_back", "Вернуться на предыдущую страницу в браузере.", {}, [], in_main=True)
def browser_back():
    def go():
        page = _page()
        page.go_back(timeout=15000)
        _settle(page)
        return _summary(page, 600)
    return _call(go)


@tool("browser_tabs", "Вкладки браузера Джарвиса: list — список, switch — переключиться, close — закрыть.",
      {"action": S("list, switch или close", enum=["list", "switch", "close"]), "index": I("Номер вкладки (с 1)")},
      [], in_main=True)
def browser_tabs(action: str = "list", index: int = 0):
    def go():
        _page()
        pages = [p for p in _state["ctx"].pages if not p.is_closed()]
        if action in ("switch", "close") and 1 <= index <= len(pages):
            p = pages[index - 1]
            if action == "close":
                p.close()
                return "Вкладка закрыта."
            _state["page"] = p
            p.bring_to_front()
            return f"Переключился: {p.title()}"
        return "\n".join(f"{i}. {p.title()[:70]} — {p.url[:80]}{' ← текущая' if p is _state['page'] else ''}"
                         for i, p in enumerate(pages, 1))
    return _call(go)


@tool("browser_look",
      "Посмотреть на текущую страницу браузера глазами (снимок) и ответить на вопрос — когда текста мало "
      "(картинки, графики, капча, вёрстка).", {"question": S("Что нужно понять")}, [], in_main=True)
def browser_look(question: str = ""):
    from .vision import FOLDER, analyse
    FOLDER.mkdir(exist_ok=True)
    path = FOLDER / f"browser_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    _call(lambda: _page().screenshot(path=str(path), type="jpeg", quality=80))
    from .screen import show as show_panel
    show_panel("Браузер", f"*{question}*" if question else "", image=str(path), panel_id="look-browser")
    return analyse(path, question) or f"Снимок страницы: {path}. Открой его (Read) и ответь: {question or 'что на нём'}."
