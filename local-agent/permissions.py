"""Explicit, local file permissions for the personal agent.

Persistent grants are read-only and directory-scoped. Destructive operations are
intentionally not exposed by this module.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

_LOCK = threading.RLock()
_SENSITIVE_NAMES = re.compile(
    r"(^|[._-])(id_rsa|id_ed25519|credentials?|secrets?|tokens?|passwords?|passwd|\.env)([._-]|$)",
    re.I,
)
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}
_SENSITIVE_EXACT = {"login data", "cookies.sqlite", "web data", "local state", "user data", "ntuser.dat"}
_MAX_RESULTS = 300


def _windows_roots() -> list[Path]:
    roots = []
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        roots.extend([system_root, Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                      Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
                      Path(os.environ.get("ProgramData", r"C:\ProgramData"))])
        profile = os.environ.get("USERPROFILE")
        if profile:
            roots.extend([Path(profile) / "AppData", Path(profile) / ".ssh"])
    else:
        roots.extend([Path("/etc"), Path("/root"), Path("/proc"), Path("/sys"), Path("/dev")])
    return [p.resolve(strict=False) for p in roots]


def resolve_user_path(raw: str) -> Path:
    raw = str(raw or "").strip().strip('"')
    if not raw or len(raw) > 1000:
        raise ValueError("יש לציין נתיב תקין")
    path = Path(raw).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError("הנתיב חייב להיות תיקייה קיימת")
    for root in _windows_roots():
        if path == root or root in path.parents:
            raise PermissionError("גישה לתיקיית מערכת או למידע רגיש חסומה")
    return path


def _sensitive(path: Path) -> bool:
    return (any(_SENSITIVE_NAMES.search(part) or part.lower() in _SENSITIVE_EXACT for part in path.parts)
            or path.suffix.lower() in _SENSITIVE_SUFFIXES)


def _check(path: Path, grants_file: Path, one_time_root: Path | None) -> None:
    path = path.resolve(strict=True)
    one_time_root = Path(one_time_root).resolve(strict=True) if one_time_root else None
    if not path.exists():
        raise FileNotFoundError("הנתיב לא נמצא")
    for root in _windows_roots():
        if path == root or root in path.parents:
            raise PermissionError("גישה לתיקיית מערכת או למידע רגיש חסומה")
    if _sensitive(path):
        raise PermissionError("הקובץ מסומן כרגיש ולא נגיש לסוכן")
    if not (one_time_root and (path == one_time_root or one_time_root in path.parents)):
        raise PermissionError("נדרשת הרשאה חד־פעמית לפעולה ולתיקייה המסוימת")


def list_files(directory: str, grants_file: Path, one_time_root: Path | None = None, limit: int = 200,
               filename_query: str | None = None) -> list[str]:
    root = resolve_user_path(directory)
    _check(root, grants_file, one_time_root)
    found = []
    visited = 0
    result_limit = min(max(1, int(limit)), _MAX_RESULTS)
    deadline = time.monotonic() + 25
    blocked = _windows_roots()
    skip_dirs = {
        ".git", "node_modules", "venv", ".venv", "__pycache__", ".cache", "cache",
        "temp", "tmp", "dist", "build", "site-packages", "windowsapps",
    }
    priority_dirs = {
        "users", "desktop", "documents", "downloads", "onedrive", "pictures", "videos",
        "music", "שולחן העבודה", "מסמכים", "הורדות",
    }
    user_profile = Path(os.environ["USERPROFILE"]).resolve(strict=False) if os.name == "nt" and os.environ.get("USERPROFILE") else None
    partial_reason = None

    for parent, dirs, files in os.walk(root, followlinks=False):
        visited += 1
        if visited > 5000:
            partial_reason = "החיפוש חלקי: הגעתי למגבלת 5,000 תיקיות."
            break
        if time.monotonic() > deadline:
            partial_reason = "החיפוש חלקי: הגעתי למגבלת 25 שניות."
            break

        kept_dirs = []
        for name in dirs:
            child = Path(parent) / name
            child_resolved = child.resolve(strict=False)
            if name.casefold() in skip_dirs or _sensitive(child):
                continue
            if any(child_resolved == b or b in child_resolved.parents for b in blocked):
                continue
            kept_dirs.append(name)

        def priority(name: str) -> tuple[int, str]:
            child = (Path(parent) / name).resolve(strict=False)
            if user_profile is not None and child == user_profile:
                return (0, name.casefold())
            return (1 if name.casefold() in priority_dirs else 2, name.casefold())

        dirs[:] = sorted(kept_dirs, key=priority)
        for name in files:
            if filename_query and filename_query not in name.casefold():
                continue
            p = Path(parent) / name
            try:
                _check(p, grants_file, one_time_root)
                found.append(str(p))
            except (OSError, PermissionError):
                continue
            if len(found) >= result_limit:
                partial_reason = f"החיפוש מציג עד {result_limit} תוצאות; ייתכנו תוצאות נוספות."
                break
        if partial_reason:
            break

    if partial_reason:
        found.append("⚠️ " + partial_reason + " תיקיות מטמון, פיתוח ומערכת דולגו. לחיפוש מלא יותר, ציין תיקייה מדויקת.")
    return found



def search_files(directory: str, query: str, grants_file: Path, one_time_root: Path | None = None, limit: int = 100) -> list[str]:
    query = str(query or "").strip().lower()
    if not query or len(query) > 200:
        raise ValueError("יש לציין שם או חלק משם לחיפוש")
    return list_files(directory, grants_file, one_time_root, limit=min(max(1, int(limit)), _MAX_RESULTS), filename_query=query)


def read_file(path: str, grants_file: Path, one_time_root: Path | None = None, max_bytes: int = 1_000_000) -> str:
    target = Path(path).expanduser().resolve(strict=True)
    if not target.is_file():
        raise ValueError("הנתיב חייב להיות קובץ")
    _check(target, grants_file, one_time_root)
    if target.stat().st_size > max_bytes:
        raise ValueError("הקובץ גדול מדי לקריאה; המגבלה היא 1MB")
    return target.read_text(encoding="utf-8", errors="replace")[:20000]