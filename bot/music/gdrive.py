"""Google Диск: папки, загрузка файлов, ссылки.

У сервисных аккаунтов Google нет своего места на Диске, поэтому бот работает от имени обычного
аккаунта через OAuth: админ один раз жмёт «Войти через Google» (/gdrive), бот получает refresh-токен.
Доступ — только drive.file: бот видит лишь файлы и папки, которые создал сам.

Структура:  🎵 Музыка Витуса / 2026-11 / Исполнитель — Название / {видео 1080p.mp4, звук.m4a, обложка.jpg}
Папке трека ставится метка appProperties.yt=<id видео> — по ней бот находит дубли даже после перезапуска.
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import aiohttp
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file", "openid", "email"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FOLDER = "application/vnd.google-apps.folder"
CHUNK = 16 * 1024 * 1024
MIME = {".mp4": "video/mp4", ".m4a": "audio/mp4", ".opus": "audio/ogg", ".webm": "audio/webm",
        ".mp3": "audio/mpeg", ".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def folder_url(fid: str) -> str:
    return f"https://drive.google.com/drive/folders/{fid}"


def file_url(fid: str) -> str:
    return f"https://drive.google.com/file/d/{fid}/view"


def auth_link(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true", "state": state,
    })


async def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(TOKEN_URL, data={"code": code, "client_id": client_id, "client_secret": client_secret,
                                           "redirect_uri": redirect_uri, "grant_type": "authorization_code"}) as r:
            data = await r.json()
    if "refresh_token" not in data:
        raise RuntimeError(data.get("error_description") or data.get("error") or "Google не вернул refresh_token")
    email = ""
    if data.get("id_token"):
        import base64
        try:
            payload = data["id_token"].split(".")[1]
            email = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("email", "")
        except Exception:
            pass
    return {"refresh_token": data["refresh_token"], "email": email}


class Drive:
    """Синхронный клиент — вызывать через asyncio.to_thread."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, root_name: str):
        creds = Credentials(None, refresh_token=refresh_token, client_id=client_id, client_secret=client_secret,
                            token_uri=TOKEN_URL)
        self.api = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.root_name = root_name
        self._folders: dict[tuple[str, str], str] = {}

    def _find_folder(self, name: str, parent: str | None) -> str | None:
        q = [f"mimeType='{FOLDER}'", "trashed=false", f"name='{name.replace(chr(39), chr(92) + chr(39))}'"]
        q.append(f"'{parent}' in parents" if parent else "'root' in parents")
        res = self.api.files().list(q=" and ".join(q), fields="files(id)", pageSize=1).execute()
        files = res.get("files") or []
        return files[0]["id"] if files else None

    def folder(self, name: str, parent: str | None = None, props: dict | None = None, create: bool = True) -> str:
        key = (parent or "root", name)
        if key in self._folders:
            return self._folders[key]
        fid = self._find_folder(name, parent)
        if not fid and create:
            body = {"name": name, "mimeType": FOLDER, "parents": [parent] if parent else []}
            if props:
                body["appProperties"] = props
            fid = self.api.files().create(body=body, fields="id").execute()["id"]
        if fid:
            self._folders[key] = fid
        return fid

    def root(self) -> str:
        return self.folder(self.root_name)

    def month_folder(self, when: datetime) -> str:
        return self.folder(when.strftime("%Y-%m"), self.root())

    def find_track(self, video_id: str) -> dict | None:
        """Уже скачанный трек: папка с меткой yt=<id>. Возвращает {folder, files:{name:id}}."""
        q = f"mimeType='{FOLDER}' and trashed=false and appProperties has {{ key='yt' and value='{video_id}' }}"
        res = self.api.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
        if not res.get("files"):
            return None
        fid = res["files"][0]["id"]
        kids = self.api.files().list(q=f"'{fid}' in parents and trashed=false",
                                     fields="files(id,name,mimeType,size)", pageSize=50).execute()
        return {"folder": fid, "name": res["files"][0]["name"], "files": kids.get("files") or []}

    def make_public(self, fid: str) -> None:
        self.api.permissions().create(fileId=fid, body={"type": "anyone", "role": "reader"}, fields="id").execute()

    def track_folder(self, name: str, video_id: str, when: datetime) -> str:
        body = {"name": name, "mimeType": FOLDER, "parents": [self.month_folder(when)], "appProperties": {"yt": video_id}}
        fid = self.api.files().create(body=body, fields="id").execute()["id"]
        self.make_public(fid)  # файлы внутри наследуют доступ «у кого есть ссылка»
        return fid

    def upload(self, path: Path, parent: str, progress: Callable[[float], None] | None = None,
               description: str = "") -> str:
        media = MediaFileUpload(str(path), mimetype=MIME.get(path.suffix.lower(), "application/octet-stream"),
                                chunksize=CHUNK, resumable=True)
        req = self.api.files().create(body={"name": path.name, "parents": [parent], "description": description[:4000]},
                                      media_body=media, fields="id")
        resp = None
        retries = 0
        while resp is None:
            try:
                status, resp = req.next_chunk()
                retries = 0
            except Exception:
                retries += 1
                if retries > 5:
                    raise
                time.sleep(2 * retries)
                continue
            if status and progress:
                progress(status.progress())
        return resp["id"]

    def about(self) -> dict:
        return self.api.about().get(fields="user(emailAddress),storageQuota").execute()
