"""Почта через IMAP/SMTP: Gmail, Яндекс, Mail.ru, Outlook и любые другие."""
import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

from . import I, S, tool
from .. import config, storage

KNOWN = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "yandex.ru": ("imap.yandex.ru", "smtp.yandex.ru"),
    "ya.ru": ("imap.yandex.ru", "smtp.yandex.ru"),
    "mail.ru": ("imap.mail.ru", "smtp.mail.ru"),
    "bk.ru": ("imap.mail.ru", "smtp.mail.ru"),
    "inbox.ru": ("imap.mail.ru", "smtp.mail.ru"),
    "list.ru": ("imap.mail.ru", "smtp.mail.ru"),
    "outlook.com": ("outlook.office365.com", "smtp.office365.com"),
    "hotmail.com": ("outlook.office365.com", "smtp.office365.com"),
}


def _hosts() -> tuple[str, str]:
    domain = config.EMAIL_ADDRESS.split("@")[-1].lower()
    imap_h, smtp_h = KNOWN.get(domain, (f"imap.{domain}", f"smtp.{domain}"))
    return config.IMAP_HOST or imap_h, config.SMTP_HOST or smtp_h


def _check():
    if not (config.EMAIL_ADDRESS and config.EMAIL_PASSWORD):
        raise RuntimeError("Почта не настроена: заполните EMAIL_ADDRESS и EMAIL_PASSWORD в файле .env")


def _dec(value) -> str:
    return str(make_header(decode_header(value or "")))


def _body(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    html = ""
    for part in parts:
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/plain":
            return text
        if ctype == "text/html" and not html:
            html = text
    if html:
        import re
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    return ""


def _imap() -> imaplib.IMAP4_SSL:
    _check()
    m = imaplib.IMAP4_SSL(_hosts()[0])
    m.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
    return m


@tool("check_email", "Проверить почту: список последних писем (по умолчанию только непрочитанные).",
      {"limit": I("Сколько писем, по умолчанию 10"),
       "unread_only": {"type": "boolean", "description": "Только непрочитанные (по умолчанию да)"}})
def check_email(limit: int = 10, unread_only: bool = True):
    m = _imap()
    try:
        m.select("INBOX", readonly=True)
        _, data = m.uid("search", None, "UNSEEN" if unread_only else "ALL")
        uids = data[0].split()[-limit:][::-1]
        if not uids:
            return "Новых писем нет"
        lines = []
        for uid in uids:
            _, msg_data = m.uid("fetch", uid, "(BODY.PEEK[])")
            msg = email.message_from_bytes(msg_data[0][1])
            sender = _dec(msg.get("From"))
            subject = _dec(msg.get("Subject")) or "(без темы)"
            snippet = " ".join(_body(msg).split())[:300]
            storage.execute("INSERT OR REPLACE INTO mail_cache (uid, sender, subject, date, snippet) VALUES (?, ?, ?, ?, ?)",
                            (uid.decode(), sender, subject, msg.get("Date", ""), snippet))
            lines.append(f"[uid {uid.decode()}] От: {sender}\nТема: {subject}\n{snippet}")
        return "\n\n".join(lines)
    finally:
        m.logout()


@tool("read_email", "Прочитать письмо целиком по uid.", {"uid": S("uid письма")}, ["uid"])
def read_email(uid: str):
    m = _imap()
    try:
        m.select("INBOX")
        _, msg_data = m.uid("fetch", uid, "(RFC822)")  # помечает прочитанным
        msg = email.message_from_bytes(msg_data[0][1])
        files = [_dec(p.get_filename()) for p in msg.walk() if p.get_content_disposition() == "attachment"]
        return (f"От: {_dec(msg.get('From'))}\nКому: {_dec(msg.get('To'))}\nДата: {msg.get('Date')}\n"
                f"Тема: {_dec(msg.get('Subject'))}\n"
                + (f"Вложения: {', '.join(files)}\n" if files else "")
                + "\n" + _body(msg)[:8000])
    finally:
        m.logout()


@tool("search_email", "Найти письма по отправителю или теме.",
      {"text": S("Кого/что искать"), "limit": I("Сколько, по умолчанию 10")}, ["text"])
def search_email(text: str, limit: int = 10):
    m = _imap()
    try:
        m.select("INBOX", readonly=True)
        m.literal = text.encode("utf-8")
        _, data = m.uid("search", "CHARSET", "UTF-8", "TEXT")
        uids = data[0].split()[-limit:][::-1]
        out = []
        for uid in uids:
            _, h = m.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            msg = email.message_from_bytes(h[0][1])
            out.append(f"[uid {uid.decode()}] {_dec(msg.get('From'))} — {_dec(msg.get('Subject'))} ({msg.get('Date')})")
        return "\n".join(out) or "Ничего не нашёл"
    finally:
        m.logout()


@tool("mark_email", "Пометить письмо прочитанным, удалить или переместить в архив/спам.",
      {"uid": S("uid письма"), "action": S("Действие", enum=["read", "unread", "delete"])}, ["uid", "action"],
      dangerous=True)
def mark_email(uid: str, action: str):
    m = _imap()
    try:
        m.select("INBOX")
        if action == "read":
            m.uid("store", uid, "+FLAGS", "\\Seen")
        elif action == "unread":
            m.uid("store", uid, "-FLAGS", "\\Seen")
        else:
            m.uid("store", uid, "+FLAGS", "\\Deleted")
            m.expunge()
        return "Готово"
    finally:
        m.logout()


@tool("send_email", "Отправить письмо.",
      {"to": S("Адрес получателя"), "subject": S("Тема"), "body": S("Текст письма")},
      ["to", "subject", "body"], dangerous=True)
def send_email(to: str, subject: str, body: str):
    _check()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.EMAIL_ADDRESS, to, subject
    msg.set_content(body)
    host = _hosts()[1]
    with smtplib.SMTP_SSL(host, 465) if "office365" not in host else smtplib.SMTP(host, 587) as s:
        if "office365" in host:
            s.starttls()
        s.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        s.send_message(msg)
    return f"Письмо отправлено: {parseaddr(to)[1] or to}"


# ---------- Разбор почты: ярлыки, папки, массовые действия ----------

def _utf7_encode(name: str) -> str:
    """Имя папки → modified UTF-7 (так IMAP хранит кириллицу: «Квитанции» → &BBoEMgQ4BEI...-)."""
    import base64
    out, buf = [], []

    def flush():
        if buf:
            b = base64.b64encode("".join(buf).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            out.append("&" + b + "-")
            buf.clear()
    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def _utf7_decode(name: str) -> str:
    import base64
    import re
    return re.sub(r"&([^-]*)-", lambda m: "&" if not m.group(1) else base64.b64decode(
        m.group(1).replace(",", "/") + "=" * (-len(m.group(1)) % 4)).decode("utf-16-be"), name)


def _is_gmail() -> bool:
    return "gmail" in _hosts()[0]


def _folders(m) -> list[str]:
    import re
    names = []
    for line in m.list()[1] or []:
        raw = line.decode(errors="replace")
        mt = re.search(r'"?([^"]+)"?\s*$', raw)
        if mt:
            names.append(_utf7_decode(mt.group(1)))
    return names


def _search(m, query: str, field: str, unread_only: bool, limit: int) -> list[bytes]:
    crit = {"from": "FROM", "subject": "SUBJECT", "text": "TEXT"}.get(field, "TEXT")
    m.literal = query.encode("utf-8")
    args = ["CHARSET", "UTF-8"] + (["UNSEEN"] if unread_only else []) + [crit]
    _, data = m.uid("search", *args)
    return data[0].split()[-limit:]


@tool("email_folders", "Список папок и ярлыков почты.")
def email_folders():
    m = _imap()
    try:
        return "\n".join(_folders(m)) or "Папок нет"
    finally:
        m.logout()


@tool("organize_email",
      "Разобрать почту массово: найти письма (по отправителю, теме или тексту) и сделать с ними действие: "
      "label — поставить ярлык/положить в папку (создаётся сама), read — пометить прочитанными, "
      "archive — убрать из входящих (в Gmail письма остаются в «Вся почта»), move — переместить в папку, "
      "delete — удалить. Используй вместо скриптов для любых операций с почтой.",
      {"query": S("Что искать: адрес/имя отправителя, слово из темы или текста"),
       "field": S("Где искать", enum=["from", "subject", "text"]),
       "action": S("Действие", enum=["label", "read", "archive", "move", "delete"]),
       "folder": S("Ярлык/папка для label и move, например «Квитанции»"),
       "unread_only": {"type": "boolean", "description": "Только непрочитанные"},
       "limit": I("Максимум писем за раз, по умолчанию 200")},
      ["query", "action"], dangerous=True)
def organize_email(query: str, action: str, field: str = "text", folder: str = "", unread_only: bool = False,
                   limit: int = 200):
    if action in ("label", "move") and not folder:
        return "Укажите ярлык или папку"
    m = _imap()
    try:
        m.select("INBOX")
        uids = _search(m, query, field, unread_only, limit)
        if not uids:
            return f"Писем по запросу «{query}» не нашёл"
        ids = b",".join(uids).decode()
        enc = _utf7_encode(folder) if folder else ""
        if folder and folder not in _folders(m):
            m.create(f'"{enc}"')
        if action == "read":
            m.uid("store", ids, "+FLAGS", "\\Seen")
        elif action == "label":
            if _is_gmail():
                m.uid("store", ids, "+X-GM-LABELS", f'"{enc}"')
            else:
                m.uid("copy", ids, f'"{enc}"')
        elif action in ("move", "archive"):
            if action == "move":
                m.uid("copy", ids, f'"{enc}"')
            elif not _is_gmail():
                if "Archive" not in _folders(m):
                    m.create("Archive")
                m.uid("copy", ids, "Archive")
            m.uid("store", ids, "+FLAGS", "\\Deleted")  # в Gmail это просто снимает ярлык «Входящие»
            m.expunge()
        elif action == "delete":
            if _is_gmail():
                m.uid("copy", ids, '"[Gmail]/Trash"' if "[Gmail]/Trash" in _folders(m) else '"[Gmail]/Корзина"')
            m.uid("store", ids, "+FLAGS", "\\Deleted")
            m.expunge()
        done = {"label": f"поставил ярлык «{folder}»", "read": "пометил прочитанными", "archive": "убрал в архив",
                "move": f"переместил в «{folder}»", "delete": "удалил"}[action]
        from ..briefing import _plural
        n = len(uids)
        return f"Готово: {n} {_plural(n, 'письмо', 'письма', 'писем')} — {done}."
    finally:
        m.logout()
