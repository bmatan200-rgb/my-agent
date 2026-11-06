        response = requests.post('https://api.openai.com/v1/responses',
            headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'},
            json=payload, timeout=120)
    except requests.RequestException:
        log.exception('OpenAI network error')
        raise HTTPException(502, 'לא ניתן להתחבר ל-OpenAI כרגע')
    if not response.ok:
        log.error('OpenAI error %s: %s', response.status_code, response.text[:600])
        if response.status_code == 429:
            raise HTTPException(502, 'הגעת למגבלת שימוש או תקציב ב-OpenAI API')
        if response.status_code in (401, 403):
            raise HTTPException(502, 'בעיה במפתח ה-API או בהרשאות המודל')
        raise HTTPException(502, 'OpenAI החזיר שגיאה. בדוק את Render Logs')
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, 'OpenAI החזיר תשובה לא תקינה')
    parts = [c.get('text', '') for item in data.get('output', [])
             if item.get('type') == 'message'
             for c in item.get('content', []) if c.get('type') == 'output_text']
    return '\n'.join(parts).strip() or 'לא התקבלה תשובת טקסט. נסה שוב.'


@app.get('/', response_class=HTMLResponse)
def home():
    return HTML


@app.get('/health')
def health():
    return {'status': 'healthy', 'openai_configured': bool(API_KEY),
            'access_token_configured': bool(ACCESS_TOKEN)}


@app.post('/chat')
def chat(data: ChatMessage, x_agent_token: str | None = Header(default=None)):
    require_auth(x_agent_token)
    return {'reply': ask_ai(data.message.strip())}
