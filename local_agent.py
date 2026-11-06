"""Local personal AI agent using Ollama. Run: python local_agent.py"""
import json
import os
from pathlib import Path
from datetime import datetime
import requests

MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DATA_DIR = Path.home() / ".personal-ai-agent"
HISTORY_FILE = DATA_DIR / "history.json"
NOTES_FILE = DATA_DIR / "notes.txt"
SYSTEM = (
    "אתה סוכן אישי כללי בעברית. עזור במחקר, תכנון, כתיבה, תכנות, "
    "ניהול משימות, מסחר מקוון ואיביי. אם אינך מחובר לכלי כלשהו, "
    "אל תטען שביצעת פעולה. אל תבצע רכישות, מחיקות, פרסום או שליחת "
    "הודעות בלי אישור מפורש. היה ברור ומדויק."
)

def load_history():
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [m for m in data if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-30:]
        except (OSError, ValueError):
            pass
    return []

def save_history(messages):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(messages[-30:], ensure_ascii=False, indent=2), encoding="utf-8")

def ask(messages):
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}] + messages[-30:], "stream": False},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]

def main():
    print("הסוכן האישי שלי | מוח מקומי חינמי:", MODEL)
    print("פקודות: /help /save טקסט /notes /clear /exit")
    messages = load_history()
    while True:
        try:
            user_input = input("\nאתה: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nלהתראות")
            break
        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/help":
            print("/save טקסט - שמירת פתק | /notes - הצגת פתקים | /clear - ניקוי שיחה | /exit - יציאה")
            continue
        if user_input == "/clear":
            messages = []
            save_history(messages)
            print("היסטוריית השיחה נוקתה.")
            continue
        if user_input.startswith("/save "):
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with NOTES_FILE.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat(timespec='minutes')}] {user_input[6:]}\n")
            print("הפתק נשמר במחשב.")
            continue
        if user_input == "/notes":
            print(NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else "אין פתקים.")
            continue
        trial = messages + [{"role": "user", "content": user_input}]
        try:
            reply = ask(trial)
        except requests.RequestException as e:
            print("לא הצלחתי להתחבר ל-Ollama. ודא שהוא פועל ושהמודל הותקן.", type(e).__name__)
            continue
        except (KeyError, ValueError):
            print("התקבלה תשובה לא תקינה מ-Ollama.")
            continue
        print("\nסוכן:", reply)
        messages = (trial + [{"role": "assistant", "content": reply}])[-30:]
        save_history(messages)

if __name__ == "__main__":
    main()
