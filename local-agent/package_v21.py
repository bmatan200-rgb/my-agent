from pathlib import Path
import zipfile,ast,json
root=Path(__file__).resolve().parent
dub=Path.home()/'video-dubbing-local'
out=root.parent/'local-agent-v2.1-update.zip'
readme="""גרסה 2.1 — עדכון למערכת הקיימת, לא מתקין למחשב חדש
הקוד כבר עודכן במחשב זה. אין צורך להתקין מחדש. רענן את הדפדפן.
שיפורים: מודל פעולות qwen3:14b, רצף עד שש פעולות עם 'ואז', אישור נפרד לכל פעולה רגישה, תיקון חישוב טבעי, שחזור מסך דיבוב, תיאום משאבים בין המודל לדיבוב.
תרגום: מודל מקומי ייעודי Marian אנגלית-עברית עם מילון מותגים. יש לבדוק ולתקן טקסט לפני יצירת קול.
בדיקות: חישוב 17 כפול 24 = 408; אישור בדיקת מחשב ולאחריו אישור נפרד למחשבון שנדחה; בחירת כלי רשימת משימות; יצירת סרטון 20 שניות ללא קריסה.
מגבלות חשובות: בדיקת תמלול חוזר גילתה שגיאות בדיבור שנוצר. איכות הדיבוב טרם אושרה. אין הבטחה לשכפול קול מדויק או סנכרון שפתיים. מוזיקת הרקע מוחלפת.
מגבלת סרטון 90 שניות, נבדקו כ-20 שניות בלבד. הפעלה מחדש של השרת קוטעת עבודה פעילה. מודל גדול עשוי להיות איטי יותר.
אין כאן שליחת מייל אוטומטית; פתיחת טיוטה בלבד. אין שירותי עיבוד בתשלום.
הארכיון אינו כולל מודלים, סביבות Python או נתונים אישיים.
שחזור: עצור את הסוכן, גבה את התיקייה הקיימת והעתק את קבצי personal_agent_complete לתיקיית הסוכן ואת קבצי video-dubbing-local לתיקיית הדיבוב. שמור config.json ונתונים קיימים.
נדרשים qwen3:14b ב-Ollama ומודל models/opus-en-he בתיקיית הדיבוב; במחשב זה כבר הותקנו. להתקנת התרגום בסביבה קיימת הפעל INSTALL_TRANSLATOR.bat.
"""
installer=r'''@echo off
set "TTS_PY=%USERPROFILE%\video-dubbing-local\.venv-tts\Scripts\python.exe"
if not exist "%TTS_PY%" (
 echo Existing dubbing Python environment not found.
 pause
 exit /b 1
)
"%TTS_PY%" -m pip install sentencepiece sacremoses
if errorlevel 1 exit /b 1
"%TTS_PY%" "%~dp0setup_translation_v21.py"
pause
'''
setup="""from pathlib import Path
from transformers import MarianMTModel,MarianTokenizer
target=Path.home()/'video-dubbing-local/models/opus-en-he'
target.mkdir(parents=True,exist_ok=True)
name='Helsinki-NLP/opus-mt-en-he'
MarianTokenizer.from_pretrained(name).save_pretrained(target)
MarianMTModel.from_pretrained(name).save_pretrained(target)
print('Translation model installed locally.')
"""
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for name in ['agent.py','action_engine.py','shared_sync.py','permissions.py','diagnostics.py','requirements.txt','start.bat','install.bat','config.example.json']:
  p=root/name
  if p.exists():
   if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
   z.write(p,'personal_agent_complete/'+name)
 for name in ['dub_8s.py','translation_glossary.json']:
  p=dub/name
  if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
  z.write(p,'video-dubbing-local/'+name)
 z.writestr('README_HE.txt',readme)
 z.writestr('INSTALL_TRANSLATOR.bat',installer)
 z.writestr('setup_translation_v21.py',setup)
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 print(json.dumps({'zip':str(out),'bytes':out.stat().st_size,'files':z.namelist()},ensure_ascii=False))