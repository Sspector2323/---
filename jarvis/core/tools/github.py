"""GitHub: все репозитории, открытые PR, проверки (CI), ветки работы Claude, синхронизация на ПК."""
import base64
import subprocess
import time
from pathlib import Path

import requests

from . import S, tool
from .. import config

API = "https://api.github.com"
_cache: dict = {}


def enabled() -> bool:
    return bool(config.GITHUB_TOKEN)


def _get(path: str, **params):
    if not enabled():
        raise RuntimeError("GitHub не подключён: вставьте GITHUB_TOKEN в ⚙ Настройках")
    r = requests.get(API + path, params=params, timeout=20, headers={
        "Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"})
    if r.status_code == 401:
        raise RuntimeError("GitHub не принял токен — он неверный или истёк, создайте новый")
    r.raise_for_status()
    return r.json()


def overview(max_age: int = 120) -> list[dict]:
    """Сводка по всем репозиториям (кэш 2 минуты, чтобы не упираться в лимиты GitHub)."""
    if _cache.get("t", 0) > time.time() - max_age:
        return _cache["data"]
    repos = []
    for r in _get("/user/repos", sort="pushed", per_page=30, affiliation="owner,collaborator"):
        full = r["full_name"]
        item = {"name": full, "url": r["html_url"], "private": r["private"], "pushed": r["pushed_at"][:16].replace("T", " "),
                "branch": r["default_branch"], "prs": [], "ci": "", "claude": []}
        try:
            item["prs"] = [{"n": p["number"], "title": p["title"], "url": p["html_url"], "branch": p["head"]["ref"]}
                           for p in _get(f"/repos/{full}/pulls", state="open", per_page=10)]
            runs = _get(f"/repos/{full}/actions/runs", per_page=1, branch=r["default_branch"]).get("workflow_runs", [])
            if runs:
                item["ci"] = runs[0]["conclusion"] or runs[0]["status"]
            item["claude"] = [b["name"] for b in _get(f"/repos/{full}/branches", per_page=100)
                              if b["name"].startswith("claude/")]
        except requests.HTTPError:
            pass
        repos.append(item)
    _cache.update(t=time.time(), data=repos)
    return repos


@tool("github_overview", "Сводка по всем репозиториям GitHub: последние изменения, открытые PR, статус проверок, "
      "ветки, в которых работает Claude в облаке.")
def github_overview():
    lines = []
    for r in overview():
        s = f"{r['name']}: обновлён {r['pushed']}"
        if r["ci"]:
            s += f", проверки: {r['ci']}"
        if r["prs"]:
            s += "; открытые PR: " + "; ".join(f"#{p['n']} {p['title']}" for p in r["prs"])
        if r["claude"]:
            s += "; ветки Claude: " + ", ".join(r["claude"])
        lines.append(s)
    return "\n".join(lines) or "Репозиториев нет"


@tool("github_commits", "Последние коммиты в репозитории (можно указать ветку).",
      {"repo": S("owner/имя, например Sspector2323/timecoder"), "branch": S("Ветка (необязательно)")}, ["repo"])
def github_commits(repo: str, branch: str | None = None):
    params = {"per_page": 10}
    if branch:
        params["sha"] = branch
    return "\n".join(f"{c['commit']['author']['date'][:16].replace('T', ' ')} {c['commit']['message'].splitlines()[0]}"
                     for c in _get(f"/repos/{repo}/commits", **params))


@tool("github_issues", "Открытые задачи (issues) в репозитории.", {"repo": S("owner/имя")}, ["repo"])
def github_issues(repo: str):
    items = [i for i in _get(f"/repos/{repo}/issues", state="open", per_page=20) if "pull_request" not in i]
    return "\n".join(f"#{i['number']} {i['title']}" for i in items) or "Открытых задач нет"


def _git(args: list[str], cwd: Path | None = None) -> str:
    auth = base64.b64encode(f"x-access-token:{config.GITHUB_TOKEN}".encode()).decode()
    r = subprocess.run(["git", "-c", f"http.extraHeader=Authorization: Basic {auth}", *args], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    lines = (r.stdout + r.stderr).strip().splitlines()
    return lines[-1] if lines else "ok"


@tool("github_sync", "Скачать (clone) все репозитории в папку проектов на компьютере, а уже скачанные — обновить (pull).",
      dangerous=True)
def github_sync():
    root = Path(config.PROJECTS_DIR).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for r in overview(max_age=0):
        name = r["name"].split("/")[1]
        path = root / name
        if (path / ".git").exists():
            out.append(f"{name}: обновлён — {_git(['pull', '--ff-only'], cwd=path)}")
        else:
            url = f"https://github.com/{r['name']}.git"
            out.append(f"{name}: скачан — {_git(['clone', url, str(path)])}")
    return "\n".join(out)
