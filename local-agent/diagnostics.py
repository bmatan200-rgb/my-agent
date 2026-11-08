"""Small privacy-conscious local failure log used by the agent's diagnostics tool."""
import datetime
import json
import threading
from pathlib import Path

_lock = threading.Lock()


def record(path: Path, tool: str, error: Exception) -> None:
    message = str(error).lower()
    if isinstance(error, TimeoutError) or "timed out" in message or "timeout" in message:
        category, hint = "timeout", "בדוק אם המודל או האתר זמינים; הגדל timeout רק אם נחוץ."
    elif isinstance(error, PermissionError) or "permission" in message or "access is denied" in message:
        category, hint = "permission", "בדוק שהנתיב אושר בממשק ושאינו תיקיית מערכת או קובץ רגיש."
    elif isinstance(error, FileNotFoundError) or "not found" in message:
        category, hint = "missing_resource", "בדוק שהקובץ, התיקייה או התוכנה עדיין קיימים."
    elif "playwright" in message or "browser" in tool:
        category, hint = "browser", "בדוק שהדפדפן מותקן ושהכתובת/הסלקטור תקינים."
    elif "connect" in message or "connection" in message:
        category, hint = "connection", "בדוק שהשירות המקומי פועל ושהכתובת בהגדרות נכונה."
    else:
        category, hint = "operation_error", "נסה שוב פעם אחת; אם נכשל, בדוק את סוג הפעולה וההרשאות."
    row = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "tool": str(tool)[:60],
           "category": category, "error_type": type(error).__name__, "hint": hint}
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        try:
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-199:]]
        except (OSError, ValueError):
            rows = []
        rows.append(row)
        temp = path.with_suffix(".tmp")
        temp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows[-200:]), encoding="utf-8")
        temp.replace(path)
        if path.stat().st_size > 0 and path.parent != Path("."):
            try:
                path.chmod(0o600)
            except OSError:
                pass


def recent(path: Path, limit: int = 15) -> list[dict]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-200:]]
    except (OSError, ValueError):
        return []
    return rows[-max(1, min(30, int(limit))):]