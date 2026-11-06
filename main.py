import os
import hmac
import logging
import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Personal AI Agent")
log = logging.getLogger("agent")
API_KEY = os.getenv("OPENAI_API_KEY", "")
ACCESS_TOKEN = os.getenv("AGENT_ACCESS_TOKEN", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

HTML = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>הסוכן האישי שלי</title>
<style>
body{font-family:Arial,sans-serif;background:#f1f4f9;margin:0;padding:20px}
.container{max-width:850px;margin:auto;background:white;border-radius:15px;overflow:hidden;box-shadow:0 5px 25px #0002}
header{background:#172b4d;color:white;padding:25px}header h1{margin:0 0 8px}
#chat{height:430px;overflow-y:auto;padding:20px}
.message{padding:13px;border-radius:12px;margin:10px 0;max-width:85%;white-space:pre-wrap;overflow-wrap:anywhere}
.bot{background:#edf1f7}.user{background:#dceafe;margin-right:auto}
form{display:flex;padding:15px;gap:10px}input{flex:1;min-width:0;padding:14px;border:1px solid #ccc;border-radius:10px;font-size:16px}
button{background:#1769e0;color:white;border:0;border-radius:10px;padding:12px 25px;cursor:pointer}
</style></head><body><div class="container">
<header><h1>🤖 הסוכן האישי שלי</h1><p>כתוב לסוכן הוראות בעברית</p></header>
<div id="chat"><div class="message bot">שלום! אני הסוכן שלך. אפשר לשאול שאלות ולבקש חיפוש מידע באינטרנט. שליחת מיילים ושליטה במחשב עדיין אינן מחוברות.</div></div>
<form id="form"><input id="message" placeholder="כתוב הוראה לסוכן..." maxlength="6000" required><button id="send">שלח</button></form>
</div><script>
const form=document.getElementById('form'),input=document.getElementById('message'),chat=document.getElementById('chat'),send=document.getElementById('send');
function add(t,k){let d=document.createElement('div');d.className='message '+k;d.textContent=t;chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d;}
form.addEventListener('submit',async e=>{
e.preventDefault();let message=input.value.trim();if(!message)return;
let token=sessionStorage.getItem('agent_token');
if(!token){token=prompt('הזן את סיסמת הגישה שהגדרת ב-Render:')||'';if(token)sessionStorage.setItem('agent_token',token);}
if(!token)return;
add(message,'user');input.value='';send.disabled=true;let waiting=add('הסוכן חושב...','bot');
try{let r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Agent-Token':token},body:JSON.stringify({message})});
let d=await r.json();if(r.status===401){sessionStorage.removeItem('agent_token');waiting.textContent='סיסמה שגויה. רענן את הדף ונסה שוב.';}
else waiting.textContent=d.reply||d.detail||'אירעה תקלה.';}
catch(e){waiting.textContent='שגיאת חיבור לשרת.';}finally{send.disabled=false;}
});
</script></body></html>"""

class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=6000)

def require_auth(token):
    if not ACCESS_TOKEN:
        raise HTTPException(503, "חסר AGENT_ACCESS_TOKEN ב-Render")
    if not token or not hmac.compare_digest(token, ACCESS_TOKEN):
        raise HTTPException(401, "סיסמת גישה שגויה")

def ask_ai(message):
    if not API_KEY:
        raise HTTPException(503, "חסר OPENAI_API_KEY ב-Render")
    payload = {
        "model": MODEL,
        "instructions": "אתה עוזר אישי בעברית. ענה באופן ברור ומדויק. השתמש בחיפוש באינטרנט כאשר נחוץ מידע עדכני. אל תטען שביצעת פעולות בעולם האמיתי. כרגע אתה יכול רק לענות ולחפש מידע.",
        "input": message,
        "tools": [{"type": "web_search"}],
        "max_output_tokens": 1200,
        "store": False
    }
    try:
        response = requests.post("https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload, timeout=120)
    except requests.RequestException:
        log.exception("OpenAI connection failed")
        raise HTTPException(502, "לא הצלחתי להתחבר לשירות AI")
    if not response.ok:
        log.error("OpenAI error %s: %s", response.status_code, response.text[:500])
        raise HTTPException(502, "שגיאה בשירות AI. בדוק את יומני Render ואת הרשאות המפתח והחיוב.")
    result = response.json()
    parts = [part.get("text", "") for item in result.get("output", [])
             if item.get("type") == "message"
             for part in item.get("content", [])
             if part.get("type") == "output_text"]
    return "\n".join(parts).strip() or "לא התקבלה תשובת טקסט."

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.get("/health")
def health():
    return {"status": "healthy", "openai_configured": bool(API_KEY), "access_token_configured": bool(ACCESS_TOKEN)}

@app.post("/chat")
def chat(data: ChatMessage, x_agent_token: str | None = Header(default=None)):
    require_auth(x_agent_token)
    return {"reply": ask_ai(data.message.strip())}
