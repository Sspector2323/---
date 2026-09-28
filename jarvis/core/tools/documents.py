"""Документы: красивый структурированный PDF из текста в разметке markdown.

PDF печатает Microsoft Edge (есть в каждой Windows 11) в фоновом режиме — без окон и лишних программ.
Файлы складываются в «Документы\\Jarvis» (папка задаётся в OUTPUT_DIR).
"""
import html
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .. import config
from . import S, tool

BROWSERS = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря")

CSS = """
@page { size: A4; margin: 16mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Inter", Arial, sans-serif; color: #1c2430; font-size: 10.5pt; line-height: 1.5;
       margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.cover { border-left: 5px solid #0f6fbf; padding: 4mm 0 4mm 6mm; margin-bottom: 7mm; }
.cover .kicker { font-size: 8pt; letter-spacing: .18em; text-transform: uppercase; color: #0f6fbf; font-weight: 600; }
.cover h1 { font-size: 22pt; line-height: 1.15; margin: 2mm 0 1.5mm; color: #0b1a2b; }
.cover .sub { font-size: 11.5pt; color: #4a5a6c; }
.cover .meta { font-size: 8.5pt; color: #7a8796; margin-top: 2.5mm; }
h1 { font-size: 16pt; color: #0b1a2b; margin: 7mm 0 2mm; }
h2 { font-size: 13pt; color: #0b1a2b; margin: 7mm 0 2.5mm; padding-bottom: 1.2mm; border-bottom: 1.5px solid #d6e4f0;
     break-after: avoid; }
h3 { font-size: 11pt; color: #0f6fbf; margin: 4.5mm 0 1.5mm; break-after: avoid; }
p { margin: 0 0 2.5mm; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin: 0 0 1.2mm; }
li::marker { color: #0f6fbf; }
ul.check { list-style: none; padding-left: 1mm; }
table { width: 100%; border-collapse: collapse; margin: 1mm 0 4mm; font-size: 9.5pt; break-inside: auto; }
th { background: #0f3b63; color: #fff; text-align: left; padding: 2mm 2.5mm; font-weight: 600; }
td { padding: 1.8mm 2.5mm; border-bottom: 1px solid #e3ebf3; vertical-align: top; }
tr:nth-child(even) td { background: #f4f8fc; }
tr { break-inside: avoid; }
.callout { background: #eef6fd; border-left: 4px solid #0f6fbf; padding: 2.5mm 4mm; margin: 2mm 0 4mm;
           border-radius: 0 2mm 2mm 0; }
.callout p:last-child { margin: 0; }
code { font-family: Consolas, monospace; background: #eef2f6; padding: 0 1mm; border-radius: 1mm; font-size: 9pt; }
pre { background: #0f1b28; color: #e6edf3; padding: 3mm 4mm; border-radius: 2mm; font-size: 8.5pt;
      white-space: pre-wrap; break-inside: avoid; }
hr { border: 0; border-top: 1px solid #d6e4f0; margin: 5mm 0; }
a { color: #0f6fbf; text-decoration: none; }
strong { color: #0b1a2b; }
.foot { margin-top: 10mm; font-size: 8pt; color: #9aa6b2; border-top: 1px solid #e3ebf3; padding-top: 2mm; }
"""


def _inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    return t


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_html(md: str) -> str:
    """Небольшой конвертер: заголовки, списки (с вложенностью и галочками), таблицы, цитаты-врезки, код."""
    out: list[str] = []
    para: list[str] = []
    lists: list[tuple[int, str]] = []  # стек открытых списков: (отступ, тег)
    lines = md.replace("\r\n", "\n").split("\n")

    def flush_para():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    def close_lists(indent: int = -1):
        while lists and lists[-1][0] > indent:
            out.append(f"</li></{lists.pop()[1]}>")

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if line.startswith("```"):
            flush_para(), close_lists()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(f"<pre>{html.escape(chr(10).join(code))}</pre>")
            i += 1
            continue
        if not line:
            flush_para()
            i += 1
            continue
        m_item = re.match(r"^(\s*)([-*•]|\d+[.)])\s+(.*)$", raw)
        if line.startswith("|") and line.count("|") >= 2:
            flush_para(), close_lists()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.fullmatch(r"[\s|:\-]+", lines[i].strip()):
                    rows.append(_cells(lines[i]))
                i += 1
            head, body = rows[0], rows[1:]
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table>")
            continue
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", line):
            flush_para(), close_lists()
            out.append("<hr>")
        elif m := re.match(r"^(#{1,4})\s+(.*)$", line):
            flush_para(), close_lists()
            level = min(len(m.group(1)), 3)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
        elif line.startswith(">"):
            flush_para(), close_lists()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append('<div class="callout">' + "".join(f"<p>{_inline(q)}</p>" for q in quote if q) + "</div>")
            continue
        elif m_item:
            flush_para()
            indent = len(m_item.group(1).replace("\t", "    "))
            tag = "ol" if m_item.group(2)[0].isdigit() else "ul"
            text = m_item.group(3)
            check = re.match(r"^\[([ xXхХ])\]\s*(.*)$", text)
            if check:
                text = ("☑ " if check.group(1).strip() else "☐ ") + check.group(2)
            if lists and indent > lists[-1][0]:
                out.append(f"<{tag}{' class=check' if check else ''}>")
                lists.append((indent, tag))
            else:
                close_lists(indent)
                if lists and lists[-1][0] == indent:
                    out.append("</li>")
                else:
                    out.append(f"<{tag}{' class=check' if check else ''}>")
                    lists.append((indent, tag))
            out.append(f"<li>{_inline(text)}")
        else:
            if lists and raw.startswith(" "):  # продолжение пункта списка
                out.append(" " + _inline(line))
            else:
                close_lists()
                para.append(line)
        i += 1
    flush_para()
    close_lists()
    return "\n".join(out)


def build_html(title: str, content: str, subtitle: str = "") -> str:
    n = datetime.now()
    body = content.strip()
    first = re.match(r"^#\s+(.+)\n?", body)
    if first and first.group(1).strip().lower() == title.strip().lower():
        body = body[first.end():]  # заголовок уже есть на обложке
    date = f"{n.day} {MONTHS[n.month - 1]} {n.year}"
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{CSS}</style></head><body>
<div class="cover"><div class="kicker">J.A.R.V.I.S. · документ</div><h1>{_inline(title)}</h1>
{f'<div class="sub">{_inline(subtitle)}</div>' if subtitle else ''}
<div class="meta">Подготовлено для: {html.escape(config.USER_NAME)} · {date}</div></div>
{markdown_to_html(body)}
<div class="foot">Составлено Джарвисом · {n:%d.%m.%Y %H:%M}</div>
</body></html>"""


def find_browser() -> str | None:
    if os.getenv("PDF_BROWSER") and Path(os.getenv("PDF_BROWSER")).exists():
        return os.getenv("PDF_BROWSER")
    for p in BROWSERS:
        p = os.path.expandvars(p)
        if "%" not in p and Path(p).exists():
            return p
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    exe = find_browser()
    if not exe:
        return False
    profile = config.DATA_DIR / "pdf_profile"  # отдельный профиль: не мешает открытому Edge
    profile.mkdir(exist_ok=True)
    pdf_path.unlink(missing_ok=True)
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={profile}", "--no-pdf-header-footer", "--print-to-pdf-no-header",
           f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()]
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.insert(1, "--no-sandbox")  # Linux под root (сервер) — иначе Chromium не стартует
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(cmd, capture_output=True, timeout=90, creationflags=flags)
    except subprocess.TimeoutExpired:
        pass
    for _ in range(20):  # файл иногда дописывается долю секунды после выхода
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        time.sleep(0.25)
    return False


def output_dir() -> Path:
    folder = Path(os.path.expandvars(config.OUTPUT_DIR)).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return (name[:80] or "Документ").strip()


def _open(path: Path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        pass


@tool("make_pdf",
      "Создать красивый структурированный PDF-документ (отчёт, план, инструкция, КП, резюме, конспект, чек-лист) "
      "и открыть его. Содержание пиши в markdown: ## разделы, ### подразделы, списки «- », нумерация «1. », "
      "таблицы «| a | b |», чек-листы «- [ ] », врезка-вывод «> ». Пиши по делу: конкретика, цифры, сроки, шаги, "
      "без вступлений и общих фраз. Первым разделом — короткое резюме (3–5 пунктов).",
      {"title": S("Заголовок документа"),
       "content": S("Полный текст документа в markdown (без заголовка — он уже на обложке)"),
       "subtitle": S("Подзаголовок: для кого / о чём, одной строкой"),
       "file_name": S("Имя файла без расширения (по умолчанию — заголовок)"),
       "open": {"type": "boolean", "description": "Открыть PDF после создания (по умолчанию да)"},
       "send_telegram": {"type": "boolean", "description": "Прислать PDF в Телеграм (если она не у компьютера)"}},
      ["title", "content"])
def make_pdf(title: str, content: str, subtitle: str = "", file_name: str = "", open: bool = True,  # noqa: A002
             send_telegram: bool = False):
    folder = output_dir()
    base = _safe_name(file_name or title)
    pdf = folder / f"{base}.pdf"
    if pdf.exists():  # не затираем прошлую версию
        pdf = folder / f"{base} {datetime.now():%Y-%m-%d %H-%M}.pdf"
    html_path = config.DATA_DIR / "last_document.html"
    html_path.write_text(build_html(title, content, subtitle), encoding="utf-8")
    if not html_to_pdf(html_path, pdf):
        keep = pdf.with_suffix(".html")
        shutil.copy(html_path, keep)
        if open:
            _open(keep)
        return (f"Не нашёл Edge/Chrome, чтобы напечатать PDF. Сохранил документ как страницу: {keep}. "
                "Её можно сохранить в PDF через Ctrl+P → «Сохранить как PDF».")
    pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    if open:
        _open(pdf)
    sent = ""
    if send_telegram:
        try:
            from ..telegram_bot import send_file
            sent = " Отправил в Телеграм." if send_file(str(pdf), title) else ""
        except Exception:  # noqa: BLE001
            sent = " В Телеграм отправить не получилось."
    return f"PDF готов и открыт: {pdf} ({pages or '?'} стр.).{sent}"
