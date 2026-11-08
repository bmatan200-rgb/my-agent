import os, json, re, threading, webbrowser, datetime, time, html, uuid
import platform, shutil, subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import requests
from bs4 import BeautifulSoup
import shared_sync
import permissions
import diagnostics
import action_engine
from urllib.parse import urlencode

BASE=Path(__file__).resolve().parent
CONFIG_PATH=BASE/'config.json'
CONFIG=json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}
def setting(name, default=''):
 return os.getenv(name, str(CONFIG.get(name, default)))
# Existing data stays in its original location unless a portable path is selected.
_data=Path(setting('AGENT_DATA_DIR',str(Path.home()/'.personal-ai-agent'))).expanduser()
HOME=(_data if _data.is_absolute() else BASE/_data).resolve(); HOME.mkdir(parents=True,exist_ok=True)
WORK=HOME/'workspace'; WORK.mkdir(exist_ok=True)
HISTORY=HOME/'chat.json'; TASKS=HOME/'tasks.json'; PERMISSIONS=HOME/'permissions.json'; JOBS_PATH=HOME/'jobs.json'; DIAGNOSTICS=HOME/'diagnostics.jsonl'
PROVIDER=setting('AI_PROVIDER','ollama')
MODEL=setting('AI_MODEL',os.getenv('OLLAMA_MODEL','qwen3:8b'))
AI_URL=setting('AI_BASE_URL','http://127.0.0.1:11434' if PROVIDER=='ollama' else 'https://api.openai.com/v1').rstrip('/')
BROWSER_CHANNEL=setting('BROWSER_CHANNEL','chromium')
PORT=int(setting('AGENT_PORT','8765'))
REMOTE_PORT=int(setting('AGENT_REMOTE_PORT','8766'))
REMOTE_HOST=setting('AGENT_REMOTE_HOST','').lower()
REMOTE_USER=setting('AGENT_REMOTE_USER','').lower()
from concurrent.futures import ThreadPoolExecutor
BROWSER_WORKER=ThreadPoolExecutor(max_workers=1)
CHAT_WORKER=ThreadPoolExecutor(max_workers=1)
CHAT_JOBS={}; CHAT_JOBS_LOCK=threading.RLock()
DUB_WORKER=ThreadPoolExecutor(max_workers=1)
MODEL_WORK_LOCK=threading.RLock()
DUB_JOBS={}; DUB_JOBS_LOCK=threading.RLock()
DUB_PROCESSES={}
DUB_CANCELLED=set()

def terminate_dub_process(proc):
 if proc is None or proc.poll() is not None:return
 try:
  if os.name=='nt':
   subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=15,check=False)
  else:proc.terminate()
 except (OSError,subprocess.TimeoutExpired):
  try:proc.kill()
  except OSError:pass

DUB_JOBS_PATH=HOME/'dub_jobs.json'
DUBBING_ROOT=Path.home()/'video-dubbing-local'
CHAT_TIMEOUT=max(15,min(360,int(setting('AI_TIMEOUT_SECONDS','240'))))
LOCK=threading.RLock()
SYSTEM='''אתה סוכן אישי כללי בעברית עם כלים. כדי להפעיל כלי החזר רק JSON תקין מהצורה {"tool":"search_web","args":{"query":"..."}}. כלים זמינים: search_web(query), read_url(url), list_files(), read_file(name), write_file(name,content), file_search(directory,query), file_list_external(directory), file_read_external(path), file_open_external(path). בבקשות לתיקייה חיצונית מפורשת יש להשתמש בכלים החיצוניים עם הנתיב שציין המשתמש; list_files() מוגבל ל-workspace. email_open(provider), diagnostic_report(), calculate(expression), browser_launch(browser), browser_open(url,browser), browser_extract(browser), browser_click(selector,browser), browser_fill(selector,text,browser), add_task(text,when), list_tasks(), computer_action(action), browser_search(service,query,browser), shared_status(), shared_memory(), shared_tasks(), shared_remember(key,value), shared_queue_task(title,notes), shared_complete_task(id,result). file_*_external, file_open_external, read_file ו-browser_extract דורשים אישור חדש לכל פעולה; אין הרשאות מתמשכות. file_open_external פותח רק סוגי מסמכים וקבצי מדיה מותרים. email_open פותח Gmail או Outlook בחלון דפדפן נפרד; המשתמש מקליד סיסמה בעצמו. קריאת תוכן בדפדפן דורשת אישור בכל פעם, והתוכן נשלח לספק המודל שמוגדר בהגדרות. אין הרשאות מתמשכות לכתיבה, מחיקה או פקודות. הגנות על קבצי מפתחות, סיסמאות ותיקיות מערכת נשארות פעילות גם לאחר אישור. אין להציג אישור בטקסט כהרשאה; רק כפתור האישור בממשק מפעיל פעולה. diagnostic_report מציג שגיאות תפעוליות אחרונות והמלצות כלליות בלבד; אין לשנות קוד או להפעיל תיקון מסוכן. shared_* הוא זיכרון/משימות משותפים על אותו מחשב, לא חיבור ישיר ל-ChatGPT Work. browser_search: service יכול להיות youtube או google בלבד. בכל כלי browser_* השדה browser אופציונלי: chrome (Google Chrome), msedge (Microsoft Edge), chromium. אם המשתמש מבקש Chrome במפורש, השתמש ב-browser=chrome; אל תחליף אותו ב-Edge. הכלי פותח חלון נפרד ואינו משתלט על פרופיל הדפדפן הרגיל. אם כלי נכשל, דווח על הכישלון, ללא המצאת הצלחה. פעולות כתיבה לזיכרון משותף ויצירת משימות דורשות אישור. פעולות מחשב מותרות: system_info, disk_usage, network_info, open_calculator, open_notepad. לכל פעולת מחשב דרוש אישור. אין כלי להרצת פקודות חופשיות או להתקנת תוכנות. אל תבצע קנייה, פרסום, שליחת מייל או מחיקה. השתמש בכלי אחד בכל פעם, מקסימום 4 פעולות. השתדל לענות בעברית באופן ענייני.'''
PENDING={}; BROWSER_SESSIONS={}; BROWSER_PLAYWRIGHT=None; ACTIVE_BROWSER_CHANNEL=None

def load(p,default):
 try: return json.loads(p.read_text(encoding='utf-8'))
 except (OSError,ValueError): return default

def save(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def recover_dub_jobs():
 previous=load(DUB_JOBS_PATH,{})
 if isinstance(previous,dict):
  for jid,job in previous.items():
   if job.get('status') in ('queued','running'):
    job.update(status='interrupted',error='השרת הופעל מחדש בזמן הדיבוב. אפשר להתחיל את הדיבוב מחדש.')
   DUB_JOBS[jid]=job
 save(DUB_JOBS_PATH,DUB_JOBS)

recover_dub_jobs()

def path_for(name):
 p=(WORK/name).resolve()
 if p==WORK.resolve() or WORK.resolve() not in p.parents: raise ValueError('גישה מותרת רק לתיקיית workspace')
 return p

def approved_directory(args):
 return str(args.get('directory',''))

COMPUTER_ACTIONS={
 'system_info':'הצגת מערכת הפעלה, מעבד וזיכרון',
 'disk_usage':'בדיקת מקום פנוי בכוננים',
 'network_info':'הצגת פרטי חיבור הרשת (ipconfig)',
 'open_calculator':'פתיחת מחשבון במחשב',
 'open_notepad':'פתיחת פנקס רשימות במחשב',
}
def sync_state():
 return shared_sync.state(BASE,CONFIG)

def sync_summary():
 state=sync_state()
 tasks=state.get('tasks',[])
 return {'connected':True,'memories':len(state.get('memories',{})),'tasks':len(tasks),'pending':sum(t.get('status')=='pending' for t in tasks)}

COMPUTER_REQUESTS={
 'בדוק את פרטי המחשב':'system_info',
 'הצג פרטי מחשב':'system_info',
 'בדוק כמה מקום פנוי יש במחשב':'disk_usage',
 'בדוק מקום פנוי':'disk_usage',
 'בדוק את חיבור הרשת':'network_info',
 'פתח מחשבון':'open_calculator',
 'פתח פנקס רשימות':'open_notepad',
}

def direct_file_command(last):
 """Route explicit searches in a named Windows drive through one-time approval."""
 phrase=str(last or '').strip().rstrip(' .!?')
 if not re.search(r'^(?:חפש|תחפש|תחפשי|מצא|תמצא|תמצאי|בדוק|תבדוק|תבדקי|הצג|תציג|תראי|תראה|רשום)\b',phrase,re.I):
  return None
 drive_match=re.search(r'(?i)([A-Z]:\\?)',phrase)
 if not drive_match:return None
 if not re.search(r'(?:קבצים?|קובץ|מסמכים?|מסמך|תיקייה|תיקיה|תוכן|תכולה|מה יש|בכונן|בתיקייה|בתיקיה)',phrase,re.I):
  return None
 drive=drive_match.group(1)
 if drive.endswith(':'):drive+='\\'
 before=phrase[:drive_match.start()]
 after=phrase[drive_match.end():].strip(' \t:;,-')
 query=''
 named=re.search(r'(?:קבצים?|קובץ|מסמכים?|מסמך)\s+(?:בשם\s+|עם\s+השם\s+|שנקרא\s+)?(.+?)\s+(?:בכונן|בתיקייה|בתיקיה)\s*$',before,re.I)
 if named:
  query=named.group(1).strip(" \"'?!.,")
 elif after and not re.match(r'^(?:בכונן|בתיקייה|בתיקיה)\b',after,re.I):
  query=after
 return {'tool':'file_list_external' if not query else 'file_search','args':{'directory':drive,**({'query':query} if query else {})}}

def computer_action(args):
 if set(args)!={'action'} or args.get('action') not in COMPUTER_ACTIONS:
  raise ValueError('פעולת מחשב לא מורשית')
 action=args['action']
 if platform.system()!='Windows':raise ValueError('פעולה זו מיועדת למחשב Windows')
 if action=='system_info':
  import ctypes
  class MemoryStatus(ctypes.Structure):
   _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
  mem=MemoryStatus();mem.length=ctypes.sizeof(mem)
  ok=ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
  return 'מערכת: '+platform.platform()+'\nמעבד: '+platform.processor()+('\nזיכרון RAM: %.1f GB; פנוי: %.1f GB'%(mem.total_phys/2**30,mem.avail_phys/2**30) if ok else '')
 if action=='disk_usage':
  result=[]
  for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
   drive=letter+':'+chr(92)
   # Only local fixed disks; avoid probing disconnected network drives.
   import ctypes
   if ctypes.windll.kernel32.GetDriveTypeW(drive)!=3:continue
   try:
    total,used,free=shutil.disk_usage(drive)
    result.append('%s פנוי %.1f GB מתוך %.1f GB'%(drive,free/2**30,total/2**30))
   except OSError:continue
  return '\n'.join(result) or 'לא נמצאו כוננים מקומיים זמינים'
 system_dir=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'
 if action=='network_info':
  import ctypes
  result=subprocess.run([str(system_dir/'ipconfig.exe')],shell=False,capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if result.returncode:raise ValueError('בדיקת הרשת נכשלה, קוד '+str(result.returncode))
  encoding='cp'+str(ctypes.windll.kernel32.GetOEMCP())
  return 'פרטי רשת מקומיים (אינם בדיקת חיבור לאינטרנט):\n'+result.stdout[:16000].decode(encoding,errors='replace')
 executable='calc.exe' if action=='open_calculator' else 'notepad.exe'
 subprocess.Popen([str(system_dir/executable)],shell=False,cwd=str(WORK),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 return 'נשלחה בקשת פתיחה ל-'+('מחשבון' if action=='open_calculator' else 'פנקס רשימות')+'. בדוק את המסך במחשב; חלון התוכנה אינו מוצג בטלפון.'

def tool_call(name,args):
 if name.startswith('browser_') or name=='email_open':
  return BROWSER_WORKER.submit(_tool_call,name,args).result(timeout=60)
 return _tool_call(name,args)

def _tool_call(name,args):
 if name=='diagnostic_report':
  rows=diagnostics.recent(DIAGNOSTICS)
  return json.dumps(rows,ensure_ascii=False) if rows else 'אין תקלות שמורות כרגע.'
 if name=='file_search':
  found=permissions.search_files(args.get('directory',''),args.get('query',''),PERMISSIONS,args.get('_approved_root'))
  return '\n'.join(found) if found else 'לא נמצאו קבצים תואמים.'
 if name=='file_list_external':
  found=permissions.list_files(args.get('directory',''),PERMISSIONS,args.get('_approved_root'))
  return '\n'.join(found) if found else 'לא נמצאו קבצים נגישים.'
 if name=='file_read_external':
  return permissions.read_file(args.get('path',''),PERMISSIONS,args.get('_approved_root'))
 if name=='file_open_external':
  target=Path(args.get('path','')).expanduser().resolve(strict=True)
  if not target.is_file():raise ValueError('הנתיב חייב להיות קובץ קיים')
  if target.suffix.lower() not in {'.pdf','.docx','.doc','.txt','.md','.csv','.xlsx','.xls','.pptx','.ppt','.rtf','.odt','.ods','.png','.jpg','.jpeg','.webp','.mp4','.mov','.mp3','.wav','.srt'}:
   raise ValueError('סוג הקובץ אינו מאושר לפתיחה דרך הסוכן')
  permissions._check(target,PERMISSIONS,args.get('_approved_root'))
  if os.name!='nt':raise ValueError('פתיחת קבצים זמינה בגרסת Windows של הסוכן')
  os.startfile(str(target))
  return 'נשלחה בקשת פתיחה לתוכנת ברירת המחדל: '+str(target)
 if name=='computer_action':return computer_action(args)
 if name=='shared_status':
  status=sync_summary()
  return 'שרת הזיכרון מחובר. פריטי זיכרון: {memories}; משימות: {tasks}; ממתינות: {pending}'.format(**status)
 if name=='shared_memory':
  memories=sync_state().get('memories',{})
  latest=sorted(memories.items(),key=lambda kv:kv[1].get('updated_at',''),reverse=True)[:25]
  return json.dumps({k:v.get('value','')[:4000] for k,v in latest},ensure_ascii=False)[:12000]
 if name=='shared_tasks':
  tasks=sync_state().get('tasks',[])
  return json.dumps(tasks[-25:],ensure_ascii=False)[:12000]
 if name=='shared_remember':
  result=shared_sync.remember(BASE,CONFIG,args.get('key'),args.get('value'))
  return 'הזיכרון המשותף נשמר בהצלחה: '+str(args.get('key',''))
 if name=='shared_queue_task':
  result=shared_sync.queue_task(BASE,CONFIG,args.get('title'),args.get('notes',''))
  return 'המשימה נרשמה בזיכרון המשותף. מזהה: '+result['task']['id']
 if name=='shared_complete_task':
  result=shared_sync.complete_task(BASE,CONFIG,args.get('id',''),args.get('result',''))
  return 'המשימה סומנה כהושלמה: '+result['task']['id']
 if name=='search_web':
  q=str(args.get('query',''))[:200]
  r=requests.get('https://www.google.com/search',params={'q':q},headers={'User-Agent':'Mozilla/5.0'},timeout=15)
  soup=BeautifulSoup(r.text,'html.parser')
  for tag in soup(['script','style','nav','footer']):tag.decompose()
  return soup.get_text(' ',strip=True)[:4500]
 if name=='read_url':
  url=str(args.get('url',''))
  if not re.match(r'^https?://',url):raise ValueError('כתובת URL לא תקינה')
  from urllib.parse import urlsplit
  import ipaddress, socket
  u=urlsplit(url)
  if u.username or u.password:raise ValueError('כתובת לא מורשית')
  for item in socket.getaddrinfo(u.hostname,None):
   ip=ipaddress.ip_address(item[4][0])
   if not ip.is_global:raise ValueError('גישה לכתובות פנימיות חסומה')
  r=requests.get(url,timeout=15,allow_redirects=False,headers={'User-Agent':'Mozilla/5.0'})
  r.raise_for_status()
  if 300<=r.status_code<400:raise ValueError('הפניות אוטומטיות חסומות')
  soup=BeautifulSoup(r.text,'html.parser')
  for tag in soup(['script','style','nav','footer']):tag.decompose()
  return soup.get_text(' ',strip=True)[:6000]
 if name=='list_files':return '\n'.join(str(x.relative_to(WORK)) for x in WORK.rglob('*') if x.is_file())[:4000] or 'אין קבצים'
 if name=='read_file':
  p=path_for(str(args.get('name','')))
  if p.suffix.lower() in ('.txt','.md','.csv','.json','.py','.html','.js'):return p.read_text(encoding='utf-8')[:12000]
  if p.suffix.lower()=='.pdf':
   from pypdf import PdfReader
   return '\n'.join(page.extract_text() or '' for page in PdfReader(str(p)).pages)[:12000]
  if p.suffix.lower()=='.docx':
   from docx import Document
   return '\n'.join(x.text for x in Document(str(p)).paragraphs)[:12000]
  if p.suffix.lower()=='.xlsx':
   from openpyxl import load_workbook
   wb=load_workbook(p,read_only=True,data_only=True)
   return '\n'.join(f'{ws.title}: '+str(list(row)) for ws in wb for row in list(ws.values)[:50])[:12000]
  raise ValueError('סוג קובץ לא נתמך')
 if name=='write_file':
  p=path_for(str(args.get('name','')))
  if p.suffix.lower() not in ('.txt','.md','.csv','.json','.py','.html','.js'):raise ValueError('סוג קובץ לא נתמך לכתיבה')
  if p.exists():raise ValueError('לא דורסים קובץ קיים')
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(str(args.get('content',''))[:50000],encoding='utf-8');return 'נשמר: '+str(p)
 if name=='calculate':
  import ast,operator
  ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow,ast.USub:operator.neg}
  def ev(n):
   if isinstance(n,ast.Constant) and type(n.value) in (int,float):return n.value
   if isinstance(n,ast.BinOp) and type(n.op) in ops:return ops[type(n.op)](ev(n.left),ev(n.right))
   if isinstance(n,ast.UnaryOp) and type(n.op) in ops:return ops[type(n.op)](ev(n.operand))
   raise ValueError('ביטוי לא נתמך')
  expr=str(args.get('expression',''))[:100];return str(ev(ast.parse(expr,mode='eval').body))
 if name=='add_task':
  when=datetime.datetime.fromisoformat(str(args.get('when','')))
  if when<datetime.datetime.now():raise ValueError('זמן המשימה בעבר')
  tasks=load(TASKS,[]);tasks.append({'text':str(args.get('text',''))[:300],'when':when.isoformat(timespec='minutes'),'done':False});save(TASKS,tasks);return 'תזכורת נשמרה. היא תוצג בדפדפן כשהאפליקציה פתוחה.'
 if name=='list_tasks':return json.dumps(load(TASKS,[]),ensure_ascii=False)
 if name.startswith('browser_') or name=='email_open':
  # All Playwright calls are serialized by BROWSER_WORKER and execute in its one thread.
  global BROWSER_PLAYWRIGHT, ACTIVE_BROWSER_CHANNEL
  from playwright.sync_api import sync_playwright
  requested=str(args.get('browser','')).lower().strip()
  channel=requested or ACTIVE_BROWSER_CHANNEL or BROWSER_CHANNEL
  if channel not in ('chromium','msedge','chrome'):
   raise ValueError('דפדפן לא נתמך. ניתן להשתמש ב-Chrome, Edge או Chromium')
  label={'chrome':'Google Chrome','msedge':'Microsoft Edge','chromium':'Chromium'}[channel]
  session=BROWSER_SESSIONS.get(channel)
  if session:
   browser,page=session
   try:
    if not browser.is_connected() or page.is_closed():session=None
   except Exception:session=None
  if not session:
   if BROWSER_PLAYWRIGHT is None:
    BROWSER_PLAYWRIGHT=sync_playwright().start()
   opts={'headless':False}
   if channel != 'chromium':opts['channel']=channel
   try:
    browser=BROWSER_PLAYWRIGHT.chromium.launch(**opts)
    page=browser.new_page()
   except Exception as exc:
    raise ValueError('לא הצלחתי לפתוח את '+label+'. בדוק שהוא מותקן במחשב ושהדפדפן לא נחסם. פרטים: '+str(exc)[:240]) from exc
   BROWSER_SESSIONS[channel]=(browser,page)
  ACTIVE_BROWSER_CHANNEL=channel
  if name=='browser_launch':
   page.bring_to_front()
   return 'נפתח חלון '+label+' בשליטת הסוכן (פרופיל דפדפן נפרד; אין גישה אוטומטית ללשוניות או לחשבונות הקיימים שלך).'
  if name=='browser_search':
   query=str(args.get('query','')).strip()
   service=args.get('service','youtube')
   if not query or len(query)>250 or service not in ('youtube','google'):
    raise ValueError('יש להזין חיפוש תקין ביוטיוב או Google')
   url=('https://www.youtube.com/results?' + urlencode({'search_query':query})) if service=='youtube' else ('https://www.google.com/search?' + urlencode({'q':query}))
   page.goto(url,wait_until='domcontentloaded',timeout=30000)
   return 'נפתחו ב-'+label+' תוצאות חיפוש '+service+': '+page.url
  if name=='browser_open':
   url=str(args.get('url',''))
   if not re.match(r'^https?://',url):raise ValueError('כתובת לא תקינה')
   page.goto(url,wait_until='domcontentloaded',timeout=30000)
   return 'נפתח ב-'+label+': '+page.url
  if name=='email_open':
   provider=str(args.get('provider','')).lower().strip()
   urls={'gmail':'https://mail.google.com/','outlook':'https://outlook.live.com/mail/'}
   if provider not in urls:raise ValueError('ספק מייל לא נתמך; בחר gmail או outlook')
   page.goto(urls[provider],wait_until='domcontentloaded',timeout=30000)
   page.bring_to_front()
   return 'נפתח אתר '+provider+' בחלון '+label+'. התחבר בעצמך; הסוכן אינו מקבל או שומר את הסיסמה.'
  if name=='browser_extract':return page.locator('body').inner_text(timeout=10000)[:8000]
  if name=='browser_click':page.locator(str(args.get('selector',''))).first.click(timeout=10000);return 'בוצעה לחיצה ב-'+label
  if name=='browser_fill':page.locator(str(args.get('selector',''))).first.fill(str(args.get('text','')),timeout=10000);return 'השדה מולא ב-'+label
 raise ValueError('כלי לא קיים')

MUTATING={'computer_action','write_file','browser_launch','browser_open','browser_search','browser_click','browser_fill','email_open','file_open_external','add_task','shared_remember','shared_queue_task','shared_complete_task'}
REQUIRES_APPROVAL={'file_search','file_list_external','file_read_external','file_open_external','read_file','browser_extract'}
TOOLS={'computer_action','search_web','read_url','list_files','read_file','write_file','file_search','file_list_external','file_read_external','file_open_external','email_open','diagnostic_report','calculate','browser_launch','browser_open','browser_search','browser_extract','browser_click','browser_fill','add_task','list_tasks','shared_status','shared_memory','shared_tasks','shared_remember','shared_queue_task','shared_complete_task'}

def ai(messages):
 if not MODEL_WORK_LOCK.acquire(blocking=False):return 'המודל עסוק כרגע בעיבוד דיבוב. המתן לסיום ונסה שוב.'
 try:return action_engine.decide(globals(),messages)
 finally:MODEL_WORK_LOCK.release()

def parse_tool(s):
 s=re.sub(r'<think>.*?</think>','',s,flags=re.S).strip()
 m=re.search(r'\{\s*"tool"\s*:',s)
 if not m:return None
 try:
  obj,_=json.JSONDecoder().raw_decode(s[m.start():]);return obj if obj.get('tool') in TOOLS and isinstance(obj.get('args',{}),dict) else None
 except (ValueError,AttributeError):return None

def direct_email_command(last):
 phrase=str(last).strip()
 if not re.search(r'(?:פתח|תפתח|לפתוח|היכנס|כניסה)',phrase):return None
 if not re.search(r'(?:מייל|אימייל|דואר|gmail|outlook|hotmail)',phrase,re.I):return None
 provider='outlook' if re.search(r'(?:outlook|hotmail)',phrase,re.I) else 'gmail'
 browser='msedge' if re.search(r'(?:אדג|edge)',phrase,re.I) else 'chrome'
 return {'tool':'email_open','args':{'provider':provider,**({'browser':browser} if browser else {})}}

def direct_browser_command(last):
 """Route explicit Hebrew browser commands to tools instead of asking the AI to guess."""
 import unicodedata
 phrase=unicodedata.normalize('NFKC',str(last)).strip().rstrip(' .!?！？')
 phrase=re.sub(r'\s+',' ',phrase)
 if not phrase:return None
 # Do not turn questions about capabilities into actions.
 if re.match(r'^(?:האם|אפשר|למה|איך|מדוע|האם אתה יכול)\b',phrase):return None
 opening=bool(re.search(r'(?:^|\s)(?:פתח|תפתח|שתפתח|לפתוח|תפעיל|הפעל|להפעיל|שיפתח)(?=\s|$)',phrase,re.I))
 chrome=bool(re.search(r'(?:^|\s)(?:גוגל\s+)?(?:כרום|chrome)(?=\s|$)',phrase,re.I) or re.search(r'(?:^|\s)בכרום(?=\s|$)',phrase,re.I))
 edge=bool(re.search(r'(?:^|\s)(?:(?:מיקרוסופט|microsoft)\s+)?(?:edge|אדג[׳’\']?)(?=\s|$)',phrase,re.I))
 channel='chrome' if chrome else 'msedge' if edge else None
 extra={'browser':channel} if channel else {}
 # Search is checked before launch, so a combined request opens results, not an empty window.
 for service,site in (('youtube',r'(?:ביוטיוב|ביו\s*טיוב|ב-?youtube|באתר\s+יוטיוב)'),('google',r'(?:בגוגל|ב-?google)(?!\s+כרום)')):
  action=r'(?:חפש|תחפש|תחפשי|חפשי|מצא|תמצא)'
  pats=(
   action+r'\s+(?:לי\s+)?'+site+r'\s+(?:את\s+)?(.+)$',
   action+r'\s+(?:לי\s+)?(?:את\s+)?(.+?)\s+'+site+r'(?:\s|$)',
  )
  for pat in pats:
   match=re.search(pat,phrase,re.I)
   if match:
    query=match.group(1).strip(' \"\'?!.,')
    query=re.sub(r'\s+(?:דרך|עם|באמצעות)\s+(?:גוגל\s+)?(?:כרום|chrome|edge|אדג)\s*$', '', query,flags=re.I)
    if query:return {'tool':'browser_search','args':{'service':service,'query':query,**extra}}
 if opening:
  if re.search(r'(?:^|\s)(?:יוטיוב|youtube)(?=\s|$)',phrase,re.I):
   return {'tool':'browser_open','args':{'url':'https://www.youtube.com',**extra}}
  # 'גוגל כרום' means Chrome browser, not google.com website.
  if re.search(r'(?:^|\s)(?:גוגל|google)(?=\s|$)',phrase,re.I) and not chrome:
   return {'tool':'browser_open','args':{'url':'https://www.google.com',**extra}}
  if channel or re.search(r'(?:^|\s)(?:ה?דפדפן|דפדפן)(?=\s|$)',phrase):
   return {'tool':'browser_launch','args':extra}
 return None

RETRY_BROWSER_REQUESTS={'נסה שוב','נסה שוב בבקשה','תנסה שוב','תנסה שוב בבקשה','עוד ניסיון','נסה מחדש'}

def retry_previous_browser_request(messages):
 """Retry only a prior *browser* request, always through a new user approval."""
 for msg in reversed(messages[:-1]):
  if msg.get('role')!='user':continue
  raw=str(msg.get('content','')).strip()
  if raw in RETRY_BROWSER_REQUESTS:continue
  # Tool output is a synthetic model message, not an instruction from the user.
  if raw.startswith('תוצאת הכלי '):continue
  # Only retry the most recent meaningful user request, not an old browser action.
  return direct_browser_command(raw)
 return None


def tool_failure(name, err):
 """Tell the user about failed actions; never let the AI reinterpret failures as success."""
 diagnostics.record(DIAGNOSTICS,name,err)
 return '❌ הפעולה '+name+' נכשלה: '+str(err)[:300]


def respond_one(messages):
 route=action_engine.routed(globals(),messages)
 if route and ('reply' in route or 'approval' in route):return route
 for _ in range(4):
  last=messages[-1].get('content','').strip().rstrip('.!?') if messages and messages[-1].get('role')=='user' else ''
  direct=COMPUTER_REQUESTS.get(last)
  file_direct=direct_file_command(last)
  email_direct=direct_email_command(last)
  if route and _ == 0:
   reply=json.dumps(route,ensure_ascii=False)
  elif file_direct:
   reply=json.dumps(file_direct,ensure_ascii=False)
  elif email_direct:
   reply=json.dumps(email_direct,ensure_ascii=False)
  elif direct:
   reply=json.dumps({'tool':'computer_action','args':{'action':direct}})
  elif last in ('בדוק חיבור לסנכרון','בדוק את החיבור לסנכרון','מצב סנכרון','בדיקת סנכרון'):
   reply=json.dumps({'tool':'shared_status','args':{}})
  elif last in ('הצג זיכרון משותף','הצג זיכרונות משותפים'):
   reply=json.dumps({'tool':'shared_memory','args':{}})
  elif last in ('הצג משימות משותפות','רשימת משימות משותפות'):
   reply=json.dumps({'tool':'shared_tasks','args':{}})
  elif last in ('הצג דוח תקלות','בדוק למה פעולה לא הצליחה','הצג אבחון'):
   reply=json.dumps({'tool':'diagnostic_report','args':{}})
  elif last.startswith(('זכור במשותף:','שמור בזיכרון המשותף:')):
   payload=last.split(':',1)[1].strip()
   if '=' not in payload:
    return {'reply':'כדי לשמור זיכרון הקלד: זכור במשותף: שם = ערך','messages':messages}
   key,value=(part.strip() for part in payload.split('=',1))
   if not key or not value:
    return {'reply':'לשמירה נדרשים שם וערך שאינם ריקים.','messages':messages}
   reply=json.dumps({'tool':'shared_remember','args':{'key':key,'value':value}},ensure_ascii=False)
  elif last.startswith('משימה משותפת:'):
   title=last.split(':',1)[1].strip()
   if not title:return {'reply':'כדי להוסיף משימה הקלד: משימה משותפת: לתאר משימה','messages':messages}
   reply=json.dumps({'tool':'shared_queue_task','args':{'title':title,'notes':''}},ensure_ascii=False)
  else:
   direct_cmd=(retry_previous_browser_request(messages) if last in RETRY_BROWSER_REQUESTS else direct_browser_command(last)) if _ == 0 else None
   if last in RETRY_BROWSER_REQUESTS and direct_cmd is None and _ == 0:
    return {'reply':'לא מצאתי בקשה קודמת לפתיחת דפדפן שאוכל לנסות שוב. כתוב למשל: פתח כרום.','messages':messages}
   reply=json.dumps(direct_cmd,ensure_ascii=False) if direct_cmd else ai(messages)
  tool=parse_tool(reply)
  if not tool:return {'reply':re.sub(r'<think>.*?</think>','',reply,flags=re.S).strip(),'messages':messages+[{'role':'assistant','content':reply}]}
  try:action_engine.validate(tool,globals())
  except ValueError as exc:return {'reply':'לא בוצעה פעולה: '+str(exc),'messages':messages}
  name,args=tool['tool'],tool.get('args',{})
  if name=='computer_action' and (set(args)!={'action'} or args.get('action') not in COMPUTER_ACTIONS):
   return {'reply':'פעולת מחשב זו אינה נתמכת. אפשר לבקש פרטי מחשב, מקום פנוי, פרטי רשת, מחשבון או פנקס רשימות.','messages':messages}
  if name in MUTATING or name in REQUIRES_APPROVAL:
   if name in REQUIRES_APPROVAL:
    root=None
    if name in ('file_search','file_list_external','file_read_external','file_open_external'):
     if name in ('file_read_external','file_open_external') and not args.get('directory'):
      args['directory']=str(Path(args.get('path','')).expanduser().parent)
     try: root=permissions.resolve_user_path(approved_directory(args))
     except Exception as e:return {'reply':tool_failure(name,e),'messages':messages}
    if name in ('file_read_external','file_open_external'):
     try: target=Path(args.get('path','')).expanduser().resolve(strict=True)
     except Exception as e:return {'reply':tool_failure(name,e),'messages':messages}
     if not (target==root or root in target.parents):return {'reply':'❌ הקובץ אינו בתוך התיקייה שביקשת לאשר.','messages':messages}
   else: root=None
   token=os.urandom(16).hex();PENDING[token]={'name':name,'args':args,'messages':messages,'created':time.monotonic(),'root':str(root) if root else None}
   desc=('במחשב: '+COMPUTER_ACTIONS[args['action']] if name=='computer_action' else f'{name}: {json.dumps(args,ensure_ascii=False)}')
   if name in ('read_file','file_read_external','browser_extract'):
    desc+='\nהתוכן שייקרא יועבר לספק המודל שהוגדר: '+PROVIDER+'.'
   if name in REQUIRES_APPROVAL: desc='נדרשת הרשאה חד־פעמית · '+desc+'\nהאישור חל על הפעולה הזאת בלבד. אין הרשאה מתמשכת.'
   return {'approval':token,'description':desc,'messages':messages}
  try:
   result=tool_call(name,args)
  except Exception as e:
   failure=tool_failure(name,e)
   return {'reply':failure,'messages':messages+[{'role':'assistant','content':failure}]}
  # Return observed tool results directly. Do not allow the model to invent a follow-up success.
  return {'reply':str(result),'messages':messages+[{'role':'assistant','content':str(result)}],'_executed':True}
  messages=messages+[{'role':'assistant','content':reply},{'role':'user','content':'תוצאת הכלי '+name+': '+str(result)[:9000]}]
 return {'reply':'בוצעו מספר צעדים. בקש ממני להמשיך אם צריך.','messages':messages}


def respond(messages, remaining=None, completed=None):
 if remaining is None and messages and str(messages[-1].get('content','')).strip().rstrip('.!?') in ('כן','אשר','מאשר','כן בבקשה','תבצע','בצע'):
  return respond_one(messages)
 completed=list(completed or [])
 if remaining is None:
  raw=str(messages[-1].get('content','')) if messages else ''
  parts=re.split(r'\s+ואז\s+(?=(?:פתח|חפש|הצג|חשב|קרא|צור|כתוב|בדוק)\b)',raw)
  remaining=parts if len(parts)>1 else [raw]
  if len(remaining)>6:return {'reply':'אפשר לבצע עד שישה שלבים בבקשה אחת. חלק את הבקשה.','messages':messages}
 while remaining:
  step=remaining[0];remaining=remaining[1:]
  context=messages+[{'role':'user','content':step}] if messages[-1].get('content')!=step else messages
  result=respond_one(context)
  if result.get('approval'):
   pending=PENDING[result['approval']]
   pending['remaining_steps']=remaining
   pending['completed_steps']=completed
   result['description']=('\n'.join(completed)+'\n\n' if completed else '')+result['description']
   return result
  reply=result.get('reply','')
  if reply.startswith('❌') or not result.pop('_executed',False):
   return {**result,'reply':'\n'.join(completed+[reply])}
  completed.append(reply)
  messages=result.get('messages',context)
 return {'reply':'\n'.join(completed),'messages':messages}

def run_plan_job(job_id,messages,remaining,completed):
 with CHAT_JOBS_LOCK:
  CHAT_JOBS[job_id]['status']='running';_persist_job_state()
 try:
  result=respond(messages,remaining,completed)
  with CHAT_JOBS_LOCK:
   if CHAT_JOBS[job_id].get('cancelled'):
    if result.get('approval'):PENDING.pop(result['approval'],None)
    CHAT_JOBS[job_id].update(status='cancelled',result={'reply':'ההמשך בוטל.'})
   else:
    CHAT_JOBS[job_id].update(status='done',result={k:v for k,v in result.items() if k!='messages'})
    if not result.get('approval'):save(HISTORY,result.get('messages',messages)[-30:])
   _persist_job_state()
 except Exception as exc:
  with CHAT_JOBS_LOCK:
   CHAT_JOBS[job_id].update(status='error',result={'reply':'המשך המשימה נכשל: '+str(exc)[:200]});_persist_job_state()


def _persist_job_state():
 with CHAT_JOBS_LOCK:
  compact={k:{'status':v.get('status'),'message':v.get('message',''),'result':v.get('result'),'updated_at':datetime.datetime.now().isoformat(timespec='seconds')} for k,v in CHAT_JOBS.items()}
  save(JOBS_PATH,compact)

def run_chat_job(job_id, message):
 with CHAT_JOBS_LOCK:
  job=CHAT_JOBS[job_id];job['status']='running';_persist_job_state()
 try:
  with LOCK:
   messages=load(HISTORY,[])[-18:]+[{'role':'user','content':message}]
  result=respond(messages)
  with CHAT_JOBS_LOCK:
   job=CHAT_JOBS[job_id]
   if job.get('cancelled'):
    for token,item in list(PENDING.items()):
     if item.get('messages')==messages:PENDING.pop(token,None)
    job.update(status='cancelled',result={'reply':'הפעולה בוטלה. לא בוצעה פעולת מחשב לאחר הביטול.'})
   else:
    if not result.get('approval'):
     with LOCK:save(HISTORY,result['messages'][-30:])
    job.update(status='done',result={k:v for k,v in result.items() if k!='messages'})
   _persist_job_state()
 except Exception as e:
  with CHAT_JOBS_LOCK:
   CHAT_JOBS[job_id].update(status='error',result={'reply':'❌ המשימה נכשלה: '+str(e)[:250]})
   _persist_job_state()

def recover_jobs():
 previous=load(JOBS_PATH,{})
 recovered={}
 for jid,record in previous.items():
  if record.get('status') in ('queued','running'):
   recovered[jid]={'status':'interrupted','message':record.get('message',''),'result':{'reply':'המשימה הופסקה כאשר הסוכן נסגר. ההודעה נשמרה; שלח אותה שוב כדי להמשיך.'},'updated_at':datetime.datetime.now().isoformat(timespec='seconds')}
  else:recovered[jid]=record
 CHAT_JOBS.update(recovered)
 save(JOBS_PATH,recovered)

recover_jobs()

PAGE='''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>הסוכן האישי שלי</title><style>
*{box-sizing:border-box}body{margin:0;background:#edf1f7;color:#19283c;font:16px Arial,sans-serif}main{height:100dvh;max-width:940px;margin:auto;background:white;display:flex;flex-direction:column;box-shadow:0 0 20px #0001}header{background:#172b4d;color:white;padding:18px 22px;display:flex;justify-content:space-between;align-items:center}h1{margin:0;font-size:21px}small{color:#c5d5ee}#messages{flex:1;overflow:auto;padding:22px}.bubble{padding:13px 16px;margin:12px 0;border-radius:14px;background:#f0f3f8;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;max-width:85%}.mine{background:#dbeafe;margin-right:auto}footer{display:flex;gap:8px;padding:12px;border-top:1px solid #ddd}textarea{flex:1;min-height:52px;resize:vertical;font:inherit;border:1px solid #b7c1ce;border-radius:10px;padding:12px}button{border:0;border-radius:9px;background:#2267d4;color:white;padding:12px;cursor:pointer}button:disabled{opacity:.5}.secondary{background:#52657f}.approve{background:#0f7a54}.deny{background:#a62b39} #fileInput,#generalFileInput{display:none}.upload-bar{display:flex;align-items:center;gap:8px;padding:9px 12px;border-top:1px solid #e7ebf0;background:#fff}.upload-btn{display:inline-flex;align-items:center;white-space:nowrap;background:#52657f;border-radius:9px;padding:12px;cursor:pointer;font-size:14px}.upload-help{font-size:12px;color:#52657f}.translation-panel{padding:8px 12px;border-top:1px solid #e7ebf0;display:flex;flex-direction:column;gap:6px}.translation-panel[hidden]{display:none}#voiceChoices[hidden]{display:none}#voiceChoices{border-top:1px solid #e7ebf0;padding:9px 12px;background:#f8fafc;display:flex;flex-direction:column;gap:8px}#voiceChoices select{min-height:38px;padding:7px;max-width:290px}.translation-panel textarea{width:100%;min-height:58px;resize:vertical;font:inherit;border:1px solid #b7c1ce;border-radius:8px;padding:8px}#fileStatus{font-size:13px;flex:1;overflow-wrap:anywhere}#notice{font-size:13px;padding:4px 18px;color:#41546e}@media(max-width:600px){.bubble{max-width:98%}#messages{padding:10px}.upload-bar{flex-wrap:wrap}.upload-help{flex-basis:100%}footer{gap:6px;padding:8px}textarea{min-width:80px}}
</style></head><body><main><header><div><h1>🤖 הסוכן האישי שלי</h1><small>גרסה 3.1 · ספריית קולות מצוירים · מוח מקומי</small></div><div><button class="secondary" id="sync">בדוק סנכרון</button> <button class="secondary" id="clear">שיחה חדשה</button></div></header><div id="notice">כלי מחשב, דפדפן, מסמכים ומייל · כל פתיחה או קריאה רגישה דורשת אישור חד־פעמי</div><div class="upload-bar" style="flex-wrap:wrap"><button class="secondary" data-command="פתח כרום">פתח כרום</button><button class="secondary" data-command="פתח אדג">פתח אדג</button><button class="secondary" data-command="פתח Gmail">פתח Gmail</button><button class="secondary" data-command="פתח Outlook">פתח Outlook</button><button class="secondary" data-command="הצג קבצים בשולחן העבודה">הצג קבצים בשולחן העבודה</button><button class="secondary" data-command="מה אתה יודע לעשות">מה אתה יודע לעשות</button></div><section id="messages"></section><div class="upload-bar"><label class="upload-btn" for="fileInput">בחר סרטון לדיבוב</label><input id="fileInput" type="file" accept="video/mp4,video/quicktime,video/x-matroska,video/webm,audio/*,.srt"><label class="upload-btn" for="generalFileInput">העלה מסמך/קובץ אחר</label><input id="generalFileInput" type="file" accept=".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls,.pptx,.ppt,.rtf,.odt,.ods,.png,.jpg,.jpeg,.webp,.mp3,.wav,.m4a,.srt"><button id="dubButton" class="secondary" hidden>הכן תרגום / הפעל דיבוב</button><button id="cancelDub" class="deny" hidden>בטל דיבוב</button><button id="downloadDub" class="secondary" hidden>הורד דיבוב</button><span class="upload-help">סרטון עד 4 GiB · קובץ כללי עד 4 GiB</span><span id="fileStatus"></span></div><div id="dubProgressArea" style="padding:4px 12px;background:#f7f9fc" hidden><div style="display:flex;justify-content:space-between"><span id="dubProgressText">מכין דיבוב...</span><span id="dubEta"></span></div><progress id="dubProgressBar" max="100" value="0" style="width:100%;height:16px"></progress></div><div class="translation-panel" id="translationPanel" hidden><label for="hebrewText">תרגום עברי (רשות, מומלץ לבדוק לפני הדיבוב)</label><textarea id="hebrewText" maxlength="200000" placeholder="אם התרגום האוטומטי משובש, כתוב כאן את הנוסח העברי שתרצה לשמוע."></textarea></div><div id="voiceChoices" hidden><label for="filmStyle">סגנון הסרט:</label><select id="filmStyle"><option value="auto">זיהוי אוטומטי (ניסיוני)</option><option value="animation">אנימציה / מצויר</option><option value="live">סרט רגיל</option><option value="mixed">משולב</option></select><div id="voiceRows"></div><small style="color:#52657f">בחר קול לכל דובר. 16 קולות בסיס + 16 סגנונות מצוירים. האפקטים אינם קולות של מדבבים מפורסמים.</small></div><footer><button class="secondary" id="mic" title="דיבור">🎙️</button><textarea id="msg" placeholder="מה תרצה לעשות?" rows="2"></textarea><button id="send">שלח</button></footer></main><script>
const area=document.getElementById('messages'),box=document.getElementById('msg'),send=document.getElementById('send'),fileInput=document.getElementById('fileInput'),fileStatus=document.getElementById('fileStatus'),dubButton=document.getElementById('dubButton'),cancelDub=document.getElementById('cancelDub'),downloadDub=document.getElementById('downloadDub'),translationPanel=document.getElementById('translationPanel'),hebrewText=document.getElementById('hebrewText'),dubProgressArea=document.getElementById('dubProgressArea'),dubProgressBar=document.getElementById('dubProgressBar'),dubProgressText=document.getElementById('dubProgressText'),dubEta=document.getElementById('dubEta');let busy=false,activeJob=null,lastUploadId=null,lastDubJob=null;
const voiceChoices=document.getElementById('voiceChoices'),voiceRows=document.getElementById('voiceRows'),filmStyle=document.getElementById('filmStyle');let customVoiceMap={};
function showVoices(review){if(!review||!Array.isArray(review.speakers)||!Array.isArray(review.voices))return;voiceChoices.hidden=false;voiceRows.replaceChildren();for(const speaker of review.speakers){const row=document.createElement('div');row.style.cssText='display:flex;align-items:center;gap:10px;margin:5px 0;flex-wrap:wrap';const name=document.createElement('label');name.textContent='דמות '+speaker.id+' ('+(speaker.suggested_type||'לא ידוע')+')';const sel=document.createElement('select');sel.dataset.speaker=speaker.id;for(const v of review.voices){const opt=document.createElement('option');opt.value=v.id;opt.textContent=v.label||v.id;sel.appendChild(opt)}sel.value=customVoiceMap[speaker.id]||speaker.voice_id;if(!sel.value&&sel.options.length)sel.selectedIndex=0;sel.onchange=()=>{customVoiceMap[speaker.id]=sel.value;localStorage.setItem('voiceMapDraft',JSON.stringify(customVoiceMap))};row.append(name,sel);voiceRows.appendChild(row)}if(review.film_style){const x=review.film_style;const label=document.createElement('small');label.textContent='זיהוי סרט: '+(x.style||'לא ידוע')+' · רמת ודאות '+Math.round((Number(x.confidence)||0)*100)+'%';voiceRows.prepend(label)}}
filmStyle.onchange=()=>localStorage.setItem('filmStyleDraft',filmStyle.value);
hebrewText.oninput=()=>localStorage.setItem('translationDraft',hebrewText.value);
function updateDubProgress(data){dubProgressArea.hidden=false;const pct=Math.max(0,Math.min(100,Number(data.percent)||0));dubProgressBar.value=pct;dubProgressText.textContent=(data.stage_label||'מעבד סרטון')+' · '+Math.round(pct)+'%';const eta=Number(data.eta_seconds);dubEta.textContent=Number.isFinite(eta)&&eta>0?'זמן משוער: '+(eta>=3600?Math.ceil(eta/3600)+' שעות':eta>=60?Math.ceil(eta/60)+' דקות':Math.ceil(eta)+' שניות'):'';if(data.status==='done'){dubProgressBar.value=100;dubProgressText.textContent='הושלם · 100%';dubEta.textContent=''}if(data.status==='cancelled'||data.status==='error'||data.status==='interrupted'){dubEta.textContent='';dubProgressText.textContent=data.status==='cancelled'?'בוטל': 'הופסק או נכשל'}}
function bubble(text,mine=false){const el=document.createElement('div');el.className='bubble'+(mine?' mine':'');el.textContent=text;area.appendChild(el);area.scrollTop=area.scrollHeight;return el}
async function req(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||'שגיאת שרת');return j}
function done(){busy=false;activeJob=null;send.disabled=false}
function showResult(data,waiting){if(data.job_id){waitJob(data.job_id,waiting);return}if(data.approval){waiting.textContent='נדרש אישור חד־פעמי: '+data.description;const row=document.createElement('div'),yes=document.createElement('button'),no=document.createElement('button');yes.className='approve';no.className='deny';yes.textContent='אשר פעולה';no.textContent='דחה';row.append(yes,no);waiting.appendChild(row);yes.onclick=()=>approve(true);no.onclick=()=>approve(false);async function approve(ok){yes.disabled=no.disabled=true;waiting.textContent='מעבד...';try{showResult(await req('/api/approve',{token:data.approval,allow:ok,}),waiting)}catch(e){waiting.textContent=e.message;done()}}}else{waiting.textContent=data.reply||'אין תשובה';done()}}
async function waitJob(id,waiting){activeJob=id;const cancel=document.createElement('button');cancel.className='deny';cancel.textContent='בטל פעולה';waiting.appendChild(cancel);cancel.onclick=async()=>{cancel.disabled=true;try{await req('/api/cancel',{job_id:id});waiting.textContent='הבקשה בוטלה. פעולות שמצריכות אישור לא יבוצעו.'}catch(e){waiting.textContent='לא הצלחתי לבטל: '+e.message}done()};for(let n=0;n<360;n++){if(activeJob!==id)return;await new Promise(r=>setTimeout(r,1000));try{const r=await fetch('/api/job?id='+encodeURIComponent(id));const d=await r.json();if(!r.ok)throw Error(d.error||'שגיאת שרת');if(d.status==='done'){showResult(d.result,waiting);return}if(d.status==='error'||d.status==='interrupted'||d.status==='cancelled'){waiting.textContent=(d.result&&d.result.reply)||'המשימה הופסקה';done();return}waiting.firstChild.textContent='חושב... ('+(n+1)+' שניות) '}catch(e){waiting.textContent='שגיאה בבדיקת מצב: '+e.message;done();return}}try{await req('/api/cancel',{job_id:id})}catch(e){}waiting.textContent='הזמן הקצוב הסתיים. אפשר לשלוח שוב לאחר בדיקת מצב המשימה.';done()}
async function submit(){const msg=box.value.trim();if(!msg||busy)return;busy=true;send.disabled=true;box.value='';bubble(msg,true);const waiting=bubble('חושב...');const id=crypto.randomUUID();try{const d=await req('/api/chat',{message:msg,request_id:id});await waitJob(d.job_id||id,waiting)}catch(e){waiting.textContent='הפעולה נכשלה: '+e.message;done()}}
document.getElementById('generalFileInput').onchange=()=>{const f=document.getElementById('generalFileInput').files[0];if(!f)return;if(f.size>4*1024*1024*1024){fileStatus.textContent='הקובץ גדול מ-4 GiB';bubble('❌ אפשר להעלות קובץ כללי עד 4 GiB.');return}fileStatus.textContent='מעלה קובץ '+f.name+'...';const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload');xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-Upload-Kind','general');xhr.setRequestHeader('X-File-Name',encodeURIComponent(f.name));xhr.timeout=7200000;xhr.onload=()=>{let d={};try{d=JSON.parse(xhr.responseText)}catch(e){}if(xhr.status<200||xhr.status>=300){fileStatus.textContent='ההעלאה נכשלה';bubble('❌ ההעלאה נכשלה: '+(d.error||'שגיאת שרת '+xhr.status));return}fileStatus.textContent='נשמר במחשב: '+f.name;bubble('✅ הקובץ נשמר במחשב בלבד. לא נשלח למודל ולא נפתח אוטומטית.\\nשם: '+d.name+'\\nנתיב: '+d.path)};xhr.onerror=()=>{fileStatus.textContent='ההעלאה נכשלה';bubble('❌ החיבור נותק בזמן ההעלאה. בדוק שהמחשב מחובר ונסה שוב.')};xhr.ontimeout=()=>{fileStatus.textContent='פג הזמן הקצוב להעלאה';bubble('❌ ההעלאה ארכה יותר מדי זמן.')};xhr.send(f)};document.querySelectorAll('[data-command]').forEach(el=>el.onclick=()=>{box.value=el.dataset.command;submit()});send.onclick=submit;box.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit()}};fileInput.onchange=()=>{const f=fileInput.files[0];if(!f)return;if(f.size>4*1024*1024*1024){fileStatus.textContent='הקובץ גדול מ-4 GiB';bubble('❌ אפשר להעלות קובץ עד 4 GiB.');fileInput.value='';return}lastUploadId=null;dubProgressArea.hidden=true;dubButton.hidden=true;downloadDub.hidden=true;translationPanel.hidden=true;hebrewText.value='';localStorage.removeItem('translationDraft');voiceChoices.hidden=true;customVoiceMap={};localStorage.removeItem('voiceMapDraft');fileStatus.textContent='מעלה '+f.name+'...';const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload');xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-Upload-Kind','video');xhr.setRequestHeader('X-File-Name',encodeURIComponent(f.name));xhr.timeout=7200000;xhr.upload.onprogress=e=>{if(e.lengthComputable)fileStatus.textContent='מעלה '+f.name+' · '+Math.round(e.loaded/e.total*100)+'%'};xhr.onload=()=>{let d={};try{d=JSON.parse(xhr.responseText)}catch(e){}if(xhr.status<200||xhr.status>=300){fileStatus.textContent='ההעלאה נכשלה';bubble('❌ ההעלאה נכשלה: '+(d.error||'שגיאת שרת '+xhr.status));return}fileStatus.textContent='הועלה: '+f.name;lastUploadId=d.upload_id;localStorage.setItem('lastVideoUpload',lastUploadId);dubButton.hidden=!/\\.(mp4|mov|mkv|webm)$/i.test(f.name);downloadDub.hidden=true;translationPanel.hidden=dubButton.hidden;bubble('✅ '+d.message+'\\nשם הקובץ: '+d.name+'\\nנשמר ב: '+d.path)};xhr.onerror=()=>{fileStatus.textContent='ההעלאה נכשלה';bubble('❌ החיבור נותק בזמן ההעלאה. בדוק שהסוכן והמחשב מחוברים ונסה שוב.')};xhr.ontimeout=()=>{fileStatus.textContent='ההעלאה ארכה יותר מדי זמן';bubble('❌ פג הזמן הקצוב להעלאה. אפשר לנסות קובץ קטן יותר או חיבור יציב יותר.')};xhr.send(f)};dubButton.onclick=async()=>{if(!lastUploadId)return;if(!confirm('להתחיל עיבוד מקומי? ללא טקסט עברי יוכן קודם תרגום לבדיקה. כשיש טקסט עברי יופעל דיבוב עד 3 שעות.'))return;dubButton.disabled=true;downloadDub.hidden=true;fileStatus.textContent='מכין דיבוב מקומי...';try{const started=await req('/api/dub',{upload_id:lastUploadId,confirmed:true,hebrew_text:hebrewText.value.trim(),translate_only:!hebrewText.value.trim(),voice_map:customVoiceMap,film_style:filmStyle.value});lastDubJob=started.job_id;localStorage.setItem('activeDubJob',lastDubJob);updateDubProgress({percent:0,stage_label:'מתחיל דיבוב'});cancelDub.hidden=false;cancelDub.disabled=false;for(let i=0;i<57600;i++){await new Promise(r=>setTimeout(r,3000));let r,d;try{r=await fetch('/api/dub-job?id='+encodeURIComponent(lastDubJob));d=await r.json()}catch(networkError){fileStatus.textContent='החיבור לשרת נקטע זמנית; מנסה להתחבר מחדש...';continue}if(!r.ok)throw Error(d.error||'לא ניתן לבדוק את מצב הדיבוב');updateDubProgress(d);if(d.status==='done'){localStorage.removeItem('activeDubJob');cancelDub.hidden=true;if(d.translation){hebrewText.value=d.translation;localStorage.setItem('translationDraft',d.translation);translationPanel.hidden=false;showVoices(d.review);dubButton.hidden=false;fileStatus.textContent='בדוק ותקן את התרגום, ואז לחץ שוב להפעלת הדיבוב';bubble('התרגום הוא טיוטה. בדוק את העברית בתיבה לפני יצירת הקול.');return}fileStatus.textContent=d.message+' · מוכן להורדה';downloadDub.hidden=false;downloadDub.onclick=()=>{window.location.href='/api/dub-download?id='+encodeURIComponent(lastDubJob)};bubble('✅ '+d.message+'\\nקובץ הפלט נשמר במחשב, ואפשר ללחוץ על „הורד דיבוב”.');return}if(d.status==='error'||d.status==='interrupted'||d.status==='cancelled'){localStorage.removeItem('activeDubJob');cancelDub.hidden=true;fileStatus.textContent='הדיבוב נכשל או הופסק';bubble('❌ הדיבוב נכשל:\\n'+(d.error||'השרת הופעל מחדש; התחל דיבוב מחדש.'));return}const tail=(d.progress||'').trim().split('\\n').slice(-1)[0];fileStatus.textContent=(d.status==='queued'?'ממתין לתור...':'הדיבוב פועל במחשב...')+(tail?' '+tail.slice(-90):'')}fileStatus.textContent='הדיבוב עדיין פועל. רענון הדף לא יפסיק אותו.'}catch(e){fileStatus.textContent='שגיאה בדיבוב';bubble('❌ '+e.message)}finally{dubButton.disabled=false;cancelDub.hidden=true}};
async function resumeDub(){try{customVoiceMap=JSON.parse(localStorage.getItem('voiceMapDraft')||'{}')}catch(e){customVoiceMap={}}filmStyle.value=localStorage.getItem('filmStyleDraft')||'auto';lastUploadId=localStorage.getItem('lastVideoUpload');if(lastUploadId){dubButton.hidden=false;translationPanel.hidden=false;hebrewText.value=localStorage.getItem('translationDraft')||''}const id=localStorage.getItem('activeDubJob');if(!id)return;lastDubJob=id;cancelDub.hidden=false;cancelDub.disabled=false;fileStatus.textContent='מתחבר מחדש למשימת הדיבוב...';for(let i=0;i<57600;i++){await new Promise(r=>setTimeout(r,3000));let r,d;try{r=await fetch('/api/dub-job?id='+encodeURIComponent(id));d=await r.json()}catch(e){fileStatus.textContent='השרת לא זמין לרגע; ממשיך לנסות...';continue}if(!r.ok){fileStatus.textContent='לא נמצא מצב הדיבוב: '+(d.error||'');return}updateDubProgress(d);if(d.status==='done'){localStorage.removeItem('activeDubJob');cancelDub.hidden=true;if(d.translation){hebrewText.value=d.translation;localStorage.setItem('translationDraft',d.translation);translationPanel.hidden=false;showVoices(d.review);dubButton.hidden=false;fileStatus.textContent='התרגום מוכן לבדיקה. תקן ולחץ שוב לדיבוב.';return}fileStatus.textContent='הדיבוב הושלם · מוכן להורדה';downloadDub.hidden=false;downloadDub.onclick=()=>{window.location.href='/api/dub-download?id='+encodeURIComponent(id)};bubble('✅ הדיבוב הסתיים. לחץ על „הורד דיבוב”.');return}if(d.status==='error'||d.status==='interrupted'||d.status==='cancelled'){localStorage.removeItem('activeDubJob');cancelDub.hidden=true;fileStatus.textContent='הדיבוב הופסק';bubble('❌ '+(d.error||'הדיבוב הופסק. אפשר להתחיל מחדש.'));return}fileStatus.textContent=(d.status==='queued'?'ממתין לתור':'הדיבוב פועל במחשב')+'...'}}
cancelDub.onclick=async()=>{
 if(!lastDubJob)return;
 cancelDub.disabled=true;
 try{
  const result=await req('/api/dub-cancel',{job_id:lastDubJob});
  fileStatus.textContent=result.message||'בקשת הביטול נשלחה. עוצר את הדיבוב...';
  bubble('🛑 '+(result.message||'הדיבוב נעצר.'));
  if(result.status==='cancelled'){
   updateDubProgress({status:'cancelled'});cancelDub.hidden=true;dubButton.disabled=false;localStorage.removeItem('activeDubJob');
  }
 }catch(e){cancelDub.disabled=false;bubble('לא ניתן לעצור את הדיבוב: '+e.message)}
};
setTimeout(resumeDub,1000);
document.getElementById('sync').onclick=async()=>{try{const r=await fetch('/api/sync-status'),d=await r.json();bubble(d.connected?'✅ הסנכרון מחובר. זיכרונות: '+d.memories+' | משימות: '+d.tasks+' | ממתינות: '+d.pending:'⚠️ '+(d.error||'הסנכרון אינו זמין'))}catch(e){bubble('⚠️ לא ניתן לבדוק סנכרון')}};
document.getElementById('clear').onclick=async()=>{if(!confirm('לנקות את היסטוריית השיחה? דיבוב פעיל וקבצים לא יימחקו.'))return;const clearBtn=document.getElementById('clear');clearBtn.disabled=true;try{await req('/api/clear',{});activeJob=null;done();area.replaceChildren();bubble('השיחה החדשה מוכנה. הדיבוב והקבצים נשארו ללא שינוי.')}catch(e){bubble('❌ לא ניתן לפתוח שיחה חדשה: '+e.message)}finally{clearBtn.disabled=false}};
document.getElementById('mic').onclick=()=>{const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){alert('הדפדפן אינו תומך בזיהוי דיבור');return}const rec=new SR();rec.lang='he-IL';rec.onresult=e=>{box.value=e.results[0][0].transcript};rec.start()};
(async()=>{try{const r=await fetch('/api/history'),d=await r.json();for(const m of d.messages)if(m.role==='user'||m.role==='assistant')bubble(m.content,m.role==='user');if(!area.children.length)bubble('שלום! אני הסוכן האישי שלך. אפשר לבקש חיפוש, קריאת קבצים, חישובים ומשימות.')}catch(e){bubble('לא הצלחתי לטעון היסטוריה')}})();
setInterval(async()=>{try{const r=await fetch('/api/due'),d=await r.json();for(const t of d.tasks)bubble('🔔 תזכורת: '+t.text)}catch(e){}},30000);
</script></body></html>'''

def get_dub_progress(job,log_text):
 stage_weights={'transcribe':(0,30,'מתמלל את הדיבור'),'translate':(30,55,'מתרגם לעברית'),
                'voices':(55,60,'מזהה דוברים ומתאים קולות'),'synthesize':(60,95,'מייצר קול עברי'),
                'background':(95,98,'מפריד דיבור מצלילי הרקע'),'mux':(98,99,'משלב רקע ודיבוב בסרטון'),'done':(100,100,'הושלם')}
 status=job.get('status','')
 if status=='done':return {'percent':100,'eta_seconds':0,'stage_label':'הושלם'}
 if status in ('cancelled','error','interrupted'):return {'percent':0,'eta_seconds':None,'stage_label':'הופסק'}
 rows=[]
 for line in log_text.splitlines():
  if 'DUB_PROGRESS|' not in line:continue
  try:
   part=line.rsplit('DUB_PROGRESS|',1)[1].strip().split('|')
   stage=part[0];completed=int(part[1]);total=max(int(part[2]),1);stamp=float(part[3])
   if stage in stage_weights:rows.append((stage,completed,total,stamp))
  except (ValueError,IndexError):continue
 if not rows:return {'percent':0,'eta_seconds':None,'stage_label':'טוען מודלים ומכין נתונים'}
 stage,completed,total,stamp=rows[-1]
 low,high,label=stage_weights[stage]
 pct=round(low+(high-low)*max(0,min(1,completed/total)),1)
 eta=None
 if stage=='synthesize':
  begins=[r for r in rows if r[0]=='synthesize' and r[1]==0]
  if begins and completed>0:
   spent=max(0,stamp-begins[-1][3])
   eta=round(spent*max(0,total-completed)/completed)
  else:
   synth_rows=[r for r in rows if r[0]=='synthesize']
   if len(synth_rows)>1:
    first=synth_rows[0]
    delta=completed-first[1]
    if delta>0:eta=round(max(0,stamp-first[3])*max(0,total-completed)/delta)
 elif stage in ('translate','transcribe'):
  relevant=[r for r in rows if r[0]==stage]
  if relevant and completed>1:
   spent=max(0,stamp-relevant[0][3])
   eta=round(spent*max(0,total-completed)/max(1,completed-relevant[0][1]))
 return {'percent':pct,'eta_seconds':eta,'stage_label':label}

def run_dub_job(job_id: str, input_path: Path, output_path: Path, log_path: Path, override_path: Path | None = None, translate_only: bool = False, voice_map_path: Path | None = None, film_style: str = 'auto') -> None:
 with DUB_JOBS_LOCK:
  if job_id in DUB_CANCELLED or DUB_JOBS[job_id]['status']=='cancelled':return
  DUB_JOBS[job_id]['status']='running'
  save(DUB_JOBS_PATH,DUB_JOBS)
 try:
  interpreter=DUBBING_ROOT/'.venv-tts'/'Scripts'/'python.exe'
  script=DUBBING_ROOT/'movie_dub.py'
  if not interpreter.is_file() or not script.is_file():
   raise FileNotFoundError('לא נמצאו קובצי ההפעלה של כלי הדיבוב המקומי.')
  env=os.environ.copy()
  env.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'})
  command=[str(interpreter),str(script),'--input',str(input_path),'--output',str(output_path)]
  if translate_only:command.append('--translate-only')
  if override_path:command.extend(['--hebrew-override',str(override_path)])
  command.extend(['--film-style',film_style])
  if voice_map_path:command.extend(['--voice-map',str(voice_map_path)])
  with MODEL_WORK_LOCK:
   with DUB_JOBS_LOCK:
    if job_id in DUB_CANCELLED:return
   with log_path.open('w',encoding='utf-8') as log:
    proc=subprocess.Popen(command,cwd=str(DUBBING_ROOT),env=env,stdout=log,stderr=subprocess.STDOUT,
      creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    with DUB_JOBS_LOCK:
     DUB_PROCESSES[job_id]=proc
     should_cancel=job_id in DUB_CANCELLED
    if should_cancel:terminate_dub_process(proc)
    try:
     result_code=proc.wait(timeout=48*3600)
    except subprocess.TimeoutExpired:
     terminate_dub_process(proc)
     raise RuntimeError('זמן הדיבוב חרג מ-48 שעות והמשימה הופסקה')
    finally:
     with DUB_JOBS_LOCK:DUB_PROCESSES.pop(job_id,None)
  with DUB_JOBS_LOCK:
   if job_id in DUB_CANCELLED:return
  translation_path=output_path.parent/(output_path.stem+'_work')/'translation.txt'
  review_path=translation_path.parent/'review.json'
  if result_code!=0 or not (translation_path.is_file() if translate_only else output_path.is_file()):
   details=log_path.read_text(encoding='utf-8',errors='replace')[-3500:] if log_path.exists() else ''
   raise RuntimeError(details or 'הדיבוב הסתיים ללא קובץ פלט.')
  with DUB_JOBS_LOCK:
   if job_id in DUB_CANCELLED:return
   DUB_JOBS[job_id].update(status='done',output_path='' if translate_only else str(output_path),
    translation=translation_path.read_text(encoding='utf-8') if translate_only else '',
    review=load(review_path,{}) if review_path.is_file() else {},
    message='התרגום מוכן לבדיקה ולאישור' if translate_only else 'הדיבוב המלא הושלם.')
   save(DUB_JOBS_PATH,DUB_JOBS)
 except Exception as exc:
  details=log_path.read_text(encoding='utf-8',errors='replace')[-3500:] if log_path.exists() else ''
  with DUB_JOBS_LOCK:
   if job_id in DUB_CANCELLED:return
   DUB_JOBS[job_id].update(status='error',error=(str(exc)+'\\n'+details)[-4000:])
   save(DUB_JOBS_PATH,DUB_JOBS)
 finally:
  with DUB_JOBS_LOCK:
   DUB_PROCESSES.pop(job_id,None)
   DUB_CANCELLED.discard(job_id)

class AgentHTTPServer(ThreadingHTTPServer):
 allow_reuse_address=False
 daemon_threads=True
 def server_bind(self):
  import socket
  if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()

class Handler(BaseHTTPRequestHandler):
 def check_access(self):
  remote=getattr(self.server,'remote_access',False)
  local_hosts=('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port))
  allowed_hosts=local_hosts+((REMOTE_HOST,REMOTE_HOST+':443') if remote else ())
  if self.headers.get('Host','').lower() not in allowed_hosts:
   self.output(403,{'error':'Host לא מורשה'});return False
  # This listener stays on loopback. Only Tailscale Serve supplies trusted remote identity.
  if remote and self.headers.get('Tailscale-User-Login','').strip().lower()!=REMOTE_USER:
   self.output(403,{'error':'חשבון Tailscale לא מורשה או חסרה זהות'});return False
  return True

 def output(self,code,data,ctype='application/json; charset=utf-8'):
  body=(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False)).encode('utf-8')
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if not self.check_access():return
  p=urlparse(self.path).path
  if p=='/':return self.output(200,PAGE,'text/html; charset=utf-8')
  if p=='/api/dub-job':
   jid=urlparse(self.path).query
   jid=jid.split('id=',1)[-1].split('&',1)[0]
   with DUB_JOBS_LOCK:job=dict(DUB_JOBS.get(jid,{}))
   if not job:return self.output(404,{'error':'משימת הדיבוב לא נמצאה או שהשרת הופעל מחדש'})
   progress=''
   progress_history=''
   log_path=Path(job.get('log_path',''))
   if log_path.is_file():
    try:
     progress_history=log_path.read_text(encoding='utf-8',errors='replace')[-40000:]
     progress=progress_history[-1200:]
    except OSError:pass
   return self.output(200,{'status':job.get('status'),'message':job.get('message',''),'error':job.get('error',''),'progress':progress,'output_path':job.get('output_path',''),'translation':job.get('translation',''),'review':job.get('review',{}),**get_dub_progress(job,progress_history)})
  if p=='/api/dub-download':
   jid=urlparse(self.path).query
   jid=jid.split('id=',1)[-1].split('&',1)[0]
   with DUB_JOBS_LOCK:job=dict(DUB_JOBS.get(jid,{}))
   if job.get('status')!='done':return self.output(404,{'error':'קובץ הדיבוב עדיין לא מוכן'})
   try:target=Path(job['output_path']).resolve(strict=True)
   except Exception:return self.output(404,{'error':'קובץ הדיבוב לא נמצא'})
   output_root=(HOME/'dubbed_outputs').resolve()
   if target.parent!=output_root or not target.is_file():return self.output(403,{'error':'נתיב קובץ לא מורשה'})
   self.send_response(200)
   self.send_header('Content-Type','video/mp4')
   self.send_header('Content-Length',str(target.stat().st_size))
   self.send_header('Content-Disposition','attachment; filename="hebrew-dub.mp4"')
   self.send_header('Cache-Control','no-store')
   self.send_header('X-Content-Type-Options','nosniff')
   self.end_headers()
   with target.open('rb') as stream:
    while True:
     chunk=stream.read(1024*1024)
     if not chunk:break
     self.wfile.write(chunk)
   return
  if p=='/api/history':return self.output(200,{'messages':load(HISTORY,[])})
  if p=='/api/job':
   jid=urlparse(self.path).query
   jid=jid.split('id=',1)[-1].split('&',1)[0]
   with CHAT_JOBS_LOCK:job=CHAT_JOBS.get(jid)
   if not job:return self.output(404,{'error':'המשימה לא נמצאה או שהשרת הופעל מחדש'})
   return self.output(200,{'status':job.get('status'),'result':job.get('result')})
  if p=='/api/sync-status':
   try:return self.output(200,sync_summary())
   except shared_sync.SyncError as e:return self.output(200,{'connected':False,'error':str(e)})
  if p=='/api/due':
   with LOCK:
    tasks=load(TASKS,[]);now=datetime.datetime.now().isoformat();due=[t for t in tasks if not t.get('done') and t['when']<=now]
    for t in due:t['done']=True
    if due:save(TASKS,tasks)
   return self.output(200,{'tasks':due})
  self.output(404,{'error':'לא נמצא'})
 def do_POST(self):
  try:
   if not self.check_access():return
   origin=self.headers.get('Origin')
   allowed_origins=(('https://'+REMOTE_HOST,) if getattr(self.server,'remote_access',False) else ('http://127.0.0.1:'+str(PORT),'http://localhost:'+str(PORT)))
   if origin and origin not in allowed_origins:
    return self.output(403,{'error':'מקור בקשה לא מורשה'})
   p=urlparse(self.path).path
   if p=='/api/upload':
    if self.headers.get('Content-Type','').split(';')[0]!='application/octet-stream':
     return self.output(415,{'error':'סוג העלאה לא נתמך'})
    n=int(self.headers.get('Content-Length','0'))
    kind=self.headers.get('X-Upload-Kind','video').strip().lower()
    limit=4*1024*1024*1024
    if n<1 or n>limit:return self.output(413,{'error':'הקובץ גדול מהמגבלה: '+('4 GiB לסרטון' if kind=='video' else '4 GiB לקובץ כללי')})
    filename=unquote(self.headers.get('X-File-Name','')).replace('\\\\','/')
    filename=Path(filename).name
    suffix=Path(filename).suffix.lower()
    video_types={'.mp4','.mov','.mkv','.webm','.mp3','.wav','.m4a','.srt'}
    general_types=video_types|{'.pdf','.docx','.doc','.txt','.md','.csv','.xlsx','.xls','.pptx','.ppt','.rtf','.odt','.ods','.png','.jpg','.jpeg','.webp'}
    allowed=video_types if kind=='video' else general_types if kind=='general' else set()
    if not filename or suffix not in allowed:
     return self.output(400,{'error':'סוג הקובץ אינו נתמך. אפשר להעלות סרטון/שמע או מסמך ותמונה נפוצים.'})
    upload_dir=HOME/'uploads';upload_dir.mkdir(parents=True,exist_ok=True)
    target=upload_dir/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8]+suffix)
    if shutil.disk_usage(upload_dir).free < n + 512*1024*1024:
     self.close_connection=True
     return self.output(507,{'error':'אין מספיק מקום פנוי בדיסק להעלאה זו'})
    self.connection.settimeout(120)
    remaining=n
    try:
     with target.open('xb') as stream:
      while remaining:
       chunk=self.rfile.read(min(1024*1024,remaining))
       if not chunk:raise ValueError('ההעלאה נקטעה באמצע')
       stream.write(chunk);remaining-=len(chunk)
    except Exception:
     try:target.unlink(missing_ok=True)
     except OSError:pass
     raise
    return self.output(200,{'ok':True,'name':filename,'upload_id':target.name,'path':str(target),'message':'הקובץ נשמר במחשב בלבד; הוא לא נשלח למודל ולא הופעל עליו עיבוד.'})
   if self.headers.get('Content-Type','').split(';')[0]!='application/json':
    return self.output(415,{'error':'נדרש JSON'})
   n=int(self.headers.get('Content-Length','0'))
   if n<0 or n>1000000:return self.output(413,{'error':'הבקשה גדולה מדי'})
   data=json.loads(self.rfile.read(n) or '{}')
   with LOCK:
    if p=='/api/dub-cancel':
     job_id=str(data.get('job_id',''))
     with DUB_JOBS_LOCK:
      job=DUB_JOBS.get(job_id)
      if not job:return self.output(404,{'error':'משימת הדיבוב לא נמצאה'})
      if job.get('status') not in ('queued','running'):
       return self.output(200,{'status':job.get('status'),'message':'המשימה כבר הסתיימה'})
      DUB_CANCELLED.add(job_id)
      job.update(status='cancelled',message='הדיבוב בוטל. הקטעים שהושלמו נשמרו להמשך.')
      save(DUB_JOBS_PATH,DUB_JOBS)
      proc=DUB_PROCESSES.get(job_id)
     if proc is not None:terminate_dub_process(proc)
     return self.output(200,{'status':'cancelled','message':'הדיבוב בוטל. אפשר להמשיך מאותו סרטון בהמשך.'})
    if p=='/api/dub':
     if data.get('confirmed') is not True:return self.output(403,{'error':'נדרש אישור מפורש להפעלת הדיבוב'})
     upload_id=str(data.get('upload_id',''))
     if Path(upload_id).name!=upload_id or Path(upload_id).suffix.lower() not in {'.mp4','.mov','.mkv','.webm'}:
      return self.output(400,{'error':'בחר סרטון MP4, MOV, MKV או WEBM שהועלה קודם'})
     upload_dir=(HOME/'uploads').resolve()
     try:input_path=(upload_dir/upload_id).resolve(strict=True)
     except Exception:return self.output(404,{'error':'הסרטון שהועלה לא נמצא. העלה אותו מחדש'})
     if input_path.parent!=upload_dir or not input_path.is_file():return self.output(403,{'error':'נתיב הסרטון אינו מורשה'})
     hebrew_text=str(data.get('hebrew_text','')).strip()
     film_style=str(data.get('film_style','auto'))
     if film_style not in ('auto','live','animation','mixed'):return self.output(400,{'error':'סגנון סרט לא תקין'})
     selected_voices=data.get('voice_map') or {}
     if not isinstance(selected_voices,dict) or len(selected_voices)>60 or any(not re.fullmatch(r'SPEAKER_\d{1,4}',str(k)) or not isinstance(v,str) or not re.fullmatch(r'[a-z0-9_]{1,64}',v) for k,v in selected_voices.items()):return self.output(400,{'error':'בחירת קולות לא תקינה'})
     if len(hebrew_text)>200000:return self.output(400,{'error':'התרגום חייב להיות עד 200,000 תווים'})
     if hebrew_text:
      has_hebrew=any(0x0590<=ord(ch)<=0x05ff for ch in hebrew_text)
      has_arabic=any(0x0600<=ord(ch)<=0x06ff for ch in hebrew_text)
      if not has_hebrew or has_arabic:return self.output(400,{'error':'התרגום חייב להיות בעברית וללא אותיות ערביות'})
     with DUB_JOBS_LOCK:
      if any(j.get('status') in ('queued','running') for j in DUB_JOBS.values()):
       return self.output(409,{'error':'כבר פועל דיבוב. המתן לסיומו לפני שמתחילים סרטון נוסף'})
      job_id=uuid.uuid4().hex
      override_path=None
      voice_map_path=None
      if hebrew_text:
       override_dir=HOME/'dub_overrides';override_dir.mkdir(parents=True,exist_ok=True)
       override_path=override_dir/(job_id+'.txt')
       override_path.write_text(hebrew_text,encoding='utf-8')
      if selected_voices:
       voice_dir=HOME/'dub_overrides';voice_dir.mkdir(parents=True,exist_ok=True)
       voice_map_path=voice_dir/(job_id+'-voices.json')
       save(voice_map_path,selected_voices)
      output_dir=HOME/'dubbed_outputs';output_dir.mkdir(parents=True,exist_ok=True)
      log_dir=HOME/'dub_logs';log_dir.mkdir(parents=True,exist_ok=True)
      output_path=output_dir/(job_id+'.mp4')
      log_path=log_dir/(job_id+'.log')
      DUB_JOBS[job_id]={'status':'queued','input_name':upload_id,'output_path':'','log_path':str(log_path),'created_at':datetime.datetime.now().isoformat(timespec='seconds')}
      save(DUB_JOBS_PATH,DUB_JOBS)
      DUB_WORKER.submit(run_dub_job,job_id,input_path,output_path,log_path,override_path,data.get('translate_only') is True,voice_map_path,film_style)
     return self.output(202,{'job_id':job_id,'status':'queued','message':'הדיבוב המקומי התחיל על כל הסרטון (עד 3 שעות)'})
    if p=='/api/clear':
     PENDING.clear()
     with CHAT_JOBS_LOCK:
      for job in CHAT_JOBS.values():
       if job.get('status') in ('queued','running'):
        job['cancelled']=True
        if job.get('status')=='queued':job.update(status='cancelled',result={'reply':'הפעולה בוטלה בעת ניקוי השיחה.'})
      _persist_job_state()
     save(HISTORY,[])
     return self.output(200,{'ok':True})
    if p=='/api/chat':
     msg=str(data.get('message','')).strip()
     if not msg or len(msg)>6000:return self.output(400,{'error':'הודעה לא תקינה'})
     request_id=str(data.get('request_id',''))
     if not re.fullmatch(r'[a-f0-9-]{20,80}',request_id):return self.output(400,{'error':'מזהה בקשה לא תקין'})
     with CHAT_JOBS_LOCK:
      if request_id in CHAT_JOBS:return self.output(200,{'job_id':request_id})
      CHAT_JOBS[request_id]={'status':'queued','message':msg,'result':None,'created_at':datetime.datetime.now().isoformat(timespec='seconds')}
      _persist_job_state()
      CHAT_WORKER.submit(run_chat_job,request_id,msg)
     return self.output(202,{'job_id':request_id})
    if p=='/api/cancel':
     jid=str(data.get('job_id',''))
     with CHAT_JOBS_LOCK:
      job=CHAT_JOBS.get(jid)
      if not job:return self.output(404,{'error':'המשימה לא נמצאה'})
      if job.get('status') in ('done','error','cancelled','interrupted'):return self.output(200,{'status':job.get('status')})
      job['cancelled']=True
      if job.get('status')=='queued':job.update(status='cancelled',result={'reply':'הפעולה בוטלה לפני שהתחילה.'})
      _persist_job_state()
     return self.output(200,{'status':'cancelled'})
    if p=='/api/approve':
     token=str(data.get('token',''));item=PENDING.pop(token,None)
     if not item or time.monotonic()-item['created']>600:return self.output(400,{'error':'האישור פג תוקף'})
     if data.get('allow') is not True:
      messages=item['messages']+[{'role':'assistant','content':'הפעולה נדחתה על ידי המשתמש.'}];save(HISTORY,messages[-30:]);return self.output(200,{'reply':'הפעולה בוטלה.'})
     # Return the actual tool result directly, with explicit failures.
     # The previous version passed errors back to the AI, which sometimes
     # invented a follow-up action (e.g. a nonexistent file).
     succeeded=False
     try:
      args=item['args']
      if item['root']:
       args['_approved_root']=item['root']
      out=tool_call(item['name'],args)
     except Exception as e:
      reply=tool_failure(item['name'],e)
     else:
      reply=str(out);succeeded=True
     messages=item['messages']+[{'role':'assistant','content':reply}]
     save(HISTORY,messages[-30:])
     if succeeded and item.get('remaining_steps'):
      jid=uuid.uuid4().hex
      with CHAT_JOBS_LOCK:
       CHAT_JOBS[jid]={'status':'queued','message':'המשך משימה','result':None};_persist_job_state()
      CHAT_WORKER.submit(run_plan_job,jid,messages,item['remaining_steps'],item.get('completed_steps',[])+[reply])
      return self.output(202,{'job_id':jid})
     return self.output(200,{'reply':'\n'.join(item.get('completed_steps',[])+[reply])})
   self.output(404,{'error':'לא נמצא'})
  except requests.RequestException as e:self.output(502,{'error':'לא ניתן להתחבר למודל או לאינטרנט. בדוק שהשירות פעיל וההגדרות נכונות.'})
  except Exception as e:self.output(500,{'error':'שגיאה: '+str(e)[:160]})

if __name__=='__main__':
 print('הסוכן האישי זמין בכתובת http://127.0.0.1:'+str(PORT))
 print('גישה מרחוק: https://'+REMOTE_HOST+' דרך Tailscale Serve בלבד')
 remote_server=AgentHTTPServer(('127.0.0.1',REMOTE_PORT),Handler)
 remote_server.remote_access=True
 threading.Thread(target=remote_server.serve_forever,daemon=True).start()
 print('לסגירה Ctrl+C.')
 threading.Timer(1,lambda:webbrowser.open('http://127.0.0.1:'+str(PORT))).start()
 AgentHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()