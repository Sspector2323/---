"""Google Sheets «База игроков»: запись каждого сообщения и чтение базы для рассылок."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import gspread

log = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))


class PlayersSheet:
    def __init__(self, service_account: dict | None, spreadsheet_id: str, gid: int):
        self._sa = service_account
        self._spreadsheet_id = spreadsheet_id
        self._gid = gid
        self._ws: gspread.Worksheet | None = None
        self._book: gspread.Spreadsheet | None = None
        self._header: list[str] | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._sa)

    def _spreadsheet(self) -> gspread.Spreadsheet:
        if self._book is None:
            client = gspread.service_account_from_dict(self._sa)
            self._book = client.open_by_key(self._spreadsheet_id)
        return self._book

    def _worksheet(self) -> gspread.Worksheet:
        if self._ws is None:
            self._ws = self._spreadsheet().get_worksheet_by_id(self._gid)
        return self._ws

    def _append_sync(self, record: dict) -> None:
        ws = self._worksheet()
        if self._header is None:
            self._header = ws.row_values(1)
        if not self._header:
            # Пустая таблица — создаём шапку как в n8n
            self._header = list(record)
            ws.append_row(self._header)
        row = [str(record.get(col, "")) for col in self._header]
        ws.append_row(row, value_input_option="RAW")

    async def log_message(self, message) -> None:
        """Аналог ноды «База игроков» (append). Ошибки не ломают ответ пользователю."""
        if not self.enabled:
            return
        user = message.from_user
        record = {
            "ID": user.id,
            "Name": user.first_name or "",
            "Username": user.username or "",
            "Date": int(message.date.timestamp()),
            "Точная дата": message.date.astimezone(MSK).strftime("%d.%m.%Y %H:%M:%S"),
            "Language": user.language_code or "",
            "text": message.text or message.caption or "",
            "Bot": str(user.is_bot).lower(),
        }
        try:
            async with self._lock:
                await asyncio.to_thread(self._append_sync, record)
        except Exception:
            self._header = None
            log.exception("Не удалось записать сообщение в Google Sheets")

    def _ids_sync(self) -> list[int]:
        values = self._worksheet().get_all_values()
        if not values:
            return []
        header = [h.strip() for h in values[0]]
        col = header.index("ID") if "ID" in header else 0
        seen: dict[int, None] = {}
        for row in values[1:]:
            try:
                seen.setdefault(int(row[col].strip()), None)
            except (ValueError, IndexError):
                continue
        return list(seen)

    async def unique_ids(self) -> list[int]:
        """Аналог «БАЗА ИГРОКОВ» + «ФИЛЬТР ОЧИСТКИ ОДИНАКОВЫХ ID»."""
        if not self.enabled:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON не задан — база недоступна")
        async with self._lock:
            return await asyncio.to_thread(self._ids_sync)


SETTINGS_SHEET = "Настройки бота"


class SettingsStore:
    """Настройки, которые админ меняет из Telegram (например, приветствие).

    Хранятся на отдельном листе «Настройки бота» той же таблицы: ключ в колонке A, значение в B.
    Файлы на Railway стираются при каждом деплое, а таблица — нет.
    """

    def __init__(self, sheet: PlayersSheet):
        self._sheet = sheet

    def _ws(self) -> gspread.Worksheet:
        book = self._sheet._spreadsheet()
        try:
            return book.worksheet(SETTINGS_SHEET)
        except gspread.WorksheetNotFound:
            return book.add_worksheet(SETTINGS_SHEET, rows=20, cols=2)

    def _get_sync(self, key: str) -> str | None:
        for row in self._ws().get_all_values():
            if row and row[0] == key:
                return row[1] if len(row) > 1 else ""
        return None

    def _set_sync(self, key: str, value: str) -> None:
        ws = self._ws()
        for i, row in enumerate(ws.get_all_values(), start=1):
            if row and row[0] == key:
                ws.update_cell(i, 2, value)
                return
        ws.append_row([key, value], value_input_option="RAW")

    async def get(self, key: str) -> str | None:
        if not self._sheet.enabled:
            return None
        return await asyncio.to_thread(self._get_sync, key)

    async def set(self, key: str, value: str) -> None:
        if not self._sheet.enabled:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON не задан — сохранить настройку негде")
        await asyncio.to_thread(self._set_sync, key, value)
