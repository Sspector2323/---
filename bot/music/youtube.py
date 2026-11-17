"""Скачивание с YouTube через yt-dlp.

Видео: до 1080p со звуком в .mp4 (дорожки склеиваются без пережатия).
Звук: отдельный файл — оригинальная дорожка YouTube без пережатия (M4A/AAC открывается везде;
MUSIC_AUDIO=best — брать Opus, если он лучше).
YouTube не отдаёт файлы серверам дата-центров («подтвердите, что вы не бот») — для этого
YOUTUBE_COOKIES (cookies запасного Google-аккаунта) и/или YOUTUBE_PROXY (домашний/резидентный прокси).
ffmpeg берём из пакета imageio-ffmpeg, JS-движок для YouTube — из пакета deno (ставятся через pip).
"""
import base64
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yt_dlp

log = logging.getLogger(__name__)

LINK_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/|live/|playlist\?[^\s]*list=)|youtu\.be/)[^\s<>\"')]+",
    re.I,
)
MAX_HEIGHT = int(os.getenv("MUSIC_MAX_HEIGHT", "1080"))
MAX_DURATION = int(os.getenv("MUSIC_MAX_MINUTES", "90")) * 60
PLAYLIST_LIMIT = 50

VIDEO_FORMAT = (
    f"bv*[height<={MAX_HEIGHT}][vcodec^=avc1]+ba[ext=m4a]/"   # H.264 + AAC — открывается везде
    f"bv*[height<={MAX_HEIGHT}]+ba/"                          # иначе лучшее до 1080p
    f"b[height<={MAX_HEIGHT}]/b"
)


_JUNK = re.compile(r"official|video|audio|lyric|visuali[sz]er|clip|\bmv\b|\b4k\b|\bhd\b|\bhq\b|remaster|"
                   r"премьера|клип|full album|album|live|extended|mix|edit|version|prod\.|ft\.|feat\.", re.I)
_LATIN_CYR = re.compile(r"[A-Za-zА-Яа-яЁё0-9]")


def parse_title(raw: str, uploader: str = "", artist: str = "", track: str = "") -> tuple[str, str, list[str]]:
    """«Artist - Title (Official Video) | Genre» → (название, исполнитель, теги)."""
    uploader = re.sub(r"\s*(- Topic|VEVO|Official|Music)$", "", uploader or "", flags=re.I).strip()
    if track and artist:
        return track.strip(), artist.split(",")[0].strip(), []
    parts = [p.strip() for p in re.split(r"\s[|｜]\s|\s//\s", raw or "") if p.strip()]
    main, extras = (parts[0] if parts else raw or ""), parts[1:]
    tags: list[str] = []

    def strip_brackets(m):
        inner = m.group(1).strip()
        if not _LATIN_CYR.search(inner):          # (द्रवसिद्धान्त), (官方) — убираем
            return ""
        if _JUNK.search(inner):
            tags.append(inner)
            return ""
        return m.group(0)
    main = re.sub(r"[(\[]([^()\[\]]*)[)\]]", strip_brackets, main)
    tail_artist = ""
    for ex in extras:                               # «Full Album (Psybient & Organic Downtempo) - Liquid Dunes»
        m_art = re.search(r"\s[-–—]\s([^()\[\]]+)$", ex)
        if m_art:
            tail_artist = tail_artist or m_art.group(1).strip()
            ex = ex[:m_art.start()]
        for piece in re.split(r"[()\[\]]", ex):
            for t in re.split(r"\s*[&,/]\s*", piece):
                if t.strip() and _LATIN_CYR.search(t):
                    tags.append(t.strip())
    main = re.sub(r"\s{2,}", " ", main).strip(" -–—|")
    who = artist.split(",")[0].strip() if artist else tail_artist
    m = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", main)
    if m and not who:
        who, main = m.group(1).strip(), m.group(2).strip()
    elif m and who and m.group(1).strip().lower() == who.lower():
        main = m.group(2).strip()
    drop = re.compile(r"official|video|clip|клип|lyric|audio|visuali[sz]er|\b4k\b|\bhd\b|\bhq\b|премьера", re.I)
    names = {x.lower() for x in (who, uploader, tail_artist) if x}
    tags = [t.strip(" -–—") for t in tags]
    tags = [t for t in dict.fromkeys(tags) if t and not drop.search(t) and len(t) <= 30 and t.lower() not in names]
    return main or raw, who or uploader, tags[:6]


def find_links(text: str) -> list[str]:
    seen, out = set(), []
    for m in LINK_RE.findall(text or ""):
        url = m.rstrip(".,;!?")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _deno() -> str | None:
    try:
        import deno
        return deno.find_deno_bin()
    except Exception:
        cand = Path(sys.executable).parent / "deno"
        return str(cand) if cand.exists() else shutil.which("deno")


def _cookiefile() -> str | None:
    """YOUTUBE_COOKIES — файл cookies (формат Netscape) целиком или в base64. Нужен, если YouTube требует вход."""
    raw = os.getenv("YOUTUBE_COOKIES", "").strip()
    if not raw:
        return None
    if not raw.startswith("#") and "\t" not in raw:
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            pass
    path = Path(tempfile.gettempdir()) / "yt_cookies.txt"
    path.write_text(raw if raw.endswith("\n") else raw + "\n", encoding="utf-8")
    return str(path)


def base_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "retries": 5, "fragment_retries": 5,
            "concurrent_fragment_downloads": 4}
    if (ff := _ffmpeg()):
        opts["ffmpeg_location"] = ff
    if (deno := _deno()):
        opts["js_runtimes"] = {"deno": {"path": deno}}
    if (cf := _cookiefile()):
        opts["cookiefile"] = cf
    if (proxy := os.getenv("YOUTUBE_PROXY", "").strip()):
        opts["proxy"] = proxy
    return opts


AUDIO_FORMAT = "ba/b" if os.getenv("MUSIC_AUDIO", "").strip().lower() == "best" else "ba[ext=m4a]/ba/b"


def explain(err: Exception) -> str:
    """Понятная причина ошибки для группы."""
    text = str(err)
    low = text.lower()
    if "not a bot" in low or "sign in to confirm" in low or "403" in low or "cookies" in low:
        return ("YouTube не пускает сервер бота (просит войти). Админу: обновить YOUTUBE_COOKIES "
                "или задать YOUTUBE_PROXY — инструкция в README.")
    if "private" in low:
        return "Видео закрытое — бот его не видит."
    if "age" in low and "confirm" in low:
        return "Видео 18+ — YouTube требует вход. Нужны YOUTUBE_COOKIES."
    if "unavailable" in low or "removed" in low:
        return "Видео недоступно или удалено."
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", text)[:300]


@dataclass
class Track:
    video_id: str
    url: str
    title: str
    uploader: str = ""
    duration: int = 0
    height: int = 0
    audio_codec: str = ""
    audio_kbps: int = 0
    tags: list[str] = field(default_factory=list)
    description: str = ""
    video_path: Path | None = None
    audio_path: Path | None = None
    cover_path: Path | None = None
    name: str = ""          # чистое название
    artist: str = ""        # исполнитель
    labels: list[str] = field(default_factory=list)  # Full Album, жанры и т.п. из названия

    @property
    def nice_title(self) -> str:
        if self.name:
            return f"{self.artist} — {self.name}" if self.artist else self.name
        t = self.title
        if " - " not in t and " — " not in t and self.uploader:
            t = f"{self.uploader.removesuffix(' - Topic')} — {t}"
        return t.replace(" - ", " — ", 1)

    @property
    def safe_name(self) -> str:
        name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", self.nice_title)
        return re.sub(r"\s+", " ", name).strip()[:120] or self.video_id

    @property
    def duration_str(self) -> str:
        m, s = divmod(self.duration or 0, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def expand(url: str) -> list[dict]:
    """Ссылка → список видео (плейлист раскрываем). Каждое: {id, url, title}."""
    # watch?v=…&list=… — только сам трек; целый плейлист — только по ссылке playlist?list=…
    opts = base_opts() | {"extract_flat": "in_playlist", "playlistend": PLAYLIST_LIMIT, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") if info.get("_type") == "playlist" else [info]
    out = []
    for e in entries or []:
        if not e or not e.get("id"):
            continue
        out.append({"id": e["id"], "url": f"https://www.youtube.com/watch?v={e['id']}", "title": e.get("title") or ""})
    return out


def download(url: str, workdir: Path, progress: Callable[[str, float], None] | None = None,
             on_info: Callable[["Track"], None] | None = None) -> Track:
    """Скачивает видео (≤1080p, mp4), лучший звук отдельно и обложку. Синхронно — вызывать в потоке."""
    workdir.mkdir(parents=True, exist_ok=True)

    def hook(stage):
        def _h(d):
            if progress and d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                progress(stage, (d.get("downloaded_bytes", 0) / total) if total else 0.0)
        return _h

    with yt_dlp.YoutubeDL(base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("is_live"):
        raise RuntimeError("Это прямой эфир — дождись, пока он закончится и станет обычным видео.")
    if MAX_DURATION and (info.get("duration") or 0) > MAX_DURATION:
        raise RuntimeError(f"Видео длиннее {MAX_DURATION // 60} минут — пропускаю.")

    track = Track(video_id=info["id"], url=info.get("webpage_url") or url, title=info.get("title") or info["id"],
                  uploader=info.get("artist") or info.get("uploader") or info.get("channel") or "",
                  duration=int(info.get("duration") or 0), tags=list(info.get("tags") or [])[:20],
                  description=(info.get("description") or "")[:2000])
    track.name, track.artist, track.labels = parse_title(
        track.title, info.get("channel") or info.get("uploader") or "", info.get("artist") or "", info.get("track") or "")
    if on_info:
        on_info(track)
    base = workdir / track.safe_name

    vopts = base_opts() | {"format": VIDEO_FORMAT, "merge_output_format": "mp4",
                           "outtmpl": f"{base} (%(height&{{}}p|video)s).%(ext)s", "progress_hooks": [hook("video")],
                           "writethumbnail": True,
                           "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}]}
    with yt_dlp.YoutubeDL(vopts) as ydl:
        vinfo = ydl.extract_info(track.url, download=True)
    track.height = int(vinfo.get("height") or 0)

    aopts = base_opts() | {"format": AUDIO_FORMAT, "outtmpl": f"{base}.%(ext)s", "progress_hooks": [hook("audio")],
                           "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "best"}]}
    with yt_dlp.YoutubeDL(aopts) as ydl:
        ainfo = ydl.extract_info(track.url, download=True)
    track.audio_codec = (ainfo.get("acodec") or "").split(".")[0]
    track.audio_kbps = int(ainfo.get("abr") or 0)

    for p in workdir.iterdir():
        if p.suffix == ".mp4":
            track.video_path = p
        elif p.suffix in {".jpg", ".jpeg", ".webp", ".png"}:
            track.cover_path = p
        elif p.suffix in {".opus", ".m4a", ".mp3", ".ogg", ".aac", ".flac", ".webm"} and p.stem == base.name:
            track.audio_path = p
    if not track.video_path:
        raise RuntimeError("Не удалось собрать видеофайл.")
    return track
