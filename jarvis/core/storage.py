"""SQLite-хранилище: задачи, напоминания, заметки, память, журнал."""
import sqlite3
import threading
from datetime import datetime

from .config import DATA_DIR

DB_PATH = DATA_DIR / "jarvis.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT DEFAULT '',
    priority TEXT DEFAULT 'обычный',
    due TEXT,
    done INTEGER DEFAULT 0,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    at TEXT NOT NULL,
    fired INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    who TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mail_cache (
    uid TEXT PRIMARY KEY,
    sender TEXT,
    subject TEXT,
    date TEXT,
    snippet TEXT
);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def execute(sql: str, params: tuple = ()) -> int:
    with _lock, _connect() as con:
        cur = con.execute(sql, params)
        return cur.lastrowid


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _lock, _connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def init() -> None:
    with _lock, _connect() as con:
        con.executescript(SCHEMA)


def log(who: str, text: str) -> None:
    execute("INSERT INTO log (ts, who, text) VALUES (?, ?, ?)", (now(), who, text))


init()
