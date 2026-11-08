from pathlib import Path
import zipfile
desktop=Path.home()/'OneDrive/שולחן העבודה'
old=desktop/'local-agent-v2.1-update.zip'
out=desktop/'local-agent-v2.2-dubbing-update.zip'
root=Path(__file__).resolve().parent
note="""עדכון דיבוב 2.2
העדכון כבר הוחל במחשב זה, ואין צורך להתקין שוב.
ברירת המחדל שונתה ליצירת קול עברי ללא דגימת הדובר באנגלית.
בבדיקת משפט עברי קבוע, דגימת הקול גרמה לשיבוש; ללא הדגימה כל המילים זוהו בתמלול חוזר.
הקול החדש אינו שכפול הקול המקורי. תמלול אוטומטי אינו תחליף להאזנה אנושית.
התרגום עדיין מצריך בדיקה ועריכה לפני יצירת קול.
הקובץ dub_8s.py.backup-v21 במחשב מאפשר חזרה לגרסה הקודמת.
"""
with zipfile.ZipFile(old) as src,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
 for item in src.infolist():
  data=src.read(item.filename)
  if item.filename=='video-dubbing-local/dub_8s.py':data=(root/'dub_8s.py').read_bytes()
  dst.writestr(item.filename,data)
 dst.writestr('UPDATE_2.2_HE.txt',note)
with zipfile.ZipFile(out) as z:assert z.testzip() is None
print(out)