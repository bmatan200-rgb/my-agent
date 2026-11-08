"""Limited, local-only client for agent-sync-starter. No external network endpoints."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

LOCAL_URL = "http://127.0.0.1:8877"

class SyncError(RuntimeError):
    pass

def token_path(app_dir, config):
    base = Path(app_dir).resolve()
    override = os.environ.get("SYNC_TOKEN_FILE") or config.get("SYNC_TOKEN_FILE") or ""
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        if candidate.is_dir():
            candidate = candidate / "private-data" / "token.txt"
        if not candidate.is_file():
            raise SyncError("קובץ ההרשאה לסנכרון לא נמצא. בדוק את SYNC_TOKEN_FILE ב-config.json")
        return candidate
    home=Path.home()
    candidates = [
        base.parent / "agent-sync-starter" / "private-data" / "token.txt",
        base / "agent-sync-starter" / "private-data" / "token.txt",
        home / "OneDrive" / "שולחן העבודה" / "agent-sync-starter" / "private-data" / "token.txt",
        home / "OneDrive" / "Desktop" / "agent-sync-starter" / "private-data" / "token.txt",
        home / "Desktop" / "agent-sync-starter" / "private-data" / "token.txt",
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise SyncError("לא נמצא קובץ ההרשאה לסנכרון. הגדר SYNC_TOKEN_FILE ב-config.json לנתיב private-data/token.txt")

def call(app_dir, config, route, payload=None):
    if config.get("SYNC_ENABLED", True) in (False, "false", "False", "0", 0):
        raise SyncError("הסנכרון כבוי בהגדרות")
    try:
        secret=token_path(app_dir, config).read_text(encoding="utf-8").strip()
        if len(secret) < 32:
            raise SyncError("קובץ ההרשאה לסנכרון לא תקין")
        headers={"Authorization": "Bearer " + secret}
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None: headers["Content-Type"] = "application/json"
        req=Request(LOCAL_URL+route, data=body, headers=headers, method="POST" if body is not None else "GET")
        with urlopen(req, timeout=5) as response:
            return json.loads(response.read(1024*1024).decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            raise SyncError("הרשאת הסנכרון שגויה. בדוק שהקובץ מתאים לשרת הפועל") from exc
        raise SyncError("שרת הסנכרון החזיר שגיאה HTTP " + str(exc.code)) from exc
    except (URLError, TimeoutError, ConnectionError) as exc:
        raise SyncError("לא ניתן להתחבר לשרת הסנכרון. הפעל node server.mjs בתיקיית agent-sync-starter") from exc
    except (OSError, ValueError, UnicodeError) as exc:
        raise SyncError("שגיאת קריאת הגדרות או תשובת שרת הסנכרון") from exc

def state(app_dir, config):
    return call(app_dir, config, "/v1/state")

def remember(app_dir, config, key, value):
    return call(app_dir, config, "/v1/memory", {"key": key, "value": value})

def queue_task(app_dir, config, title, notes=""):
    return call(app_dir, config, "/v1/tasks", {"title": title, "notes": notes})

def complete_task(app_dir, config, task_id, result=""):
    import re
    if not re.fullmatch(r"[a-f0-9-]{36}", task_id):
        raise SyncError("מזהה משימה לא תקין")
    return call(app_dir, config, "/v1/tasks/" + task_id + "/complete", {"result": result})