import os
import base64
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="eBay AI Agent")

CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")

HTML = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>סוכן eBay</title>
<style>
body {
    font-family: Arial;
    background: #f1f4f9;
    margin: 0;
    padding: 20px;
}
.container {
    max-width: 850px;
    margin: auto;
    background: white;
    border-radius: 15px;
    overflow: hidden;
    box-shadow: 0 5px 25px #0002;
}
header {
    background: #172b4d;
    color: white;
    padding: 25px;
}
header h1 { margin: 0 0 8px; }
#chat {
    height: 430px;
    overflow-y: auto;
    padding: 20px;
}
.message {
    padding: 13px;
    border-radius: 12px;
    margin: 10px 0;
    max-width: 85%;
    white-space: pre-wrap;
}
.bot { background: #edf1f7; }
.user { background: #dceafe; margin-right: auto; }
form {
    display: flex;
    padding: 15px;
    gap: 10px;
}
input {
    flex: 1;
    padding: 14px;
    border: 1px solid #ccc;
    border-radius: 10px;
    font-size: 16px;
}
button {
    background: #1769e0;
    color: white;
    border: 0;
    border-radius: 10px;
    padding: 12px 25px;
    cursor: pointer;
}
.card {
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 12px;
    margin: 10px 0;
}
.card a { color: #1769e0; }
.price { font-weight: bold; margin-top: 8px; }
</style>
</head>
<body>
<div class="container">
<header>
<h1>🤖 סוכן eBay שלי</h1>
<p>כתוב לסוכן הוראות בעברית</p>
</header>

<div id="chat">
<div class="message bot">
שלום! אני סוכן ה-eBay שלך.

אפשר לבקש ממני:
• חפש שואב אבק לרכב
• מצא גאדג'טים מבוקשים
• חפש אוזניות אלחוטיות
• הצג מוצרים מעניינים למכירה

במה נתחיל?
</div>
</div>

<form id="form">
<input id="message" placeholder="כתוב הוראה לסוכן..." required>
<button id="send">שלח</button>
</form>
</div>

<script>
const form = document.getElementById("form");
const input = document.getElementById("message");
const chat = document.getElementById("chat");
const send = document.getElementById("send");

function addMessage(text, type) {
    const div = document.createElement("div");
    div.className = "message " + type;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

form.addEventListener("submit", async function(e) {
    e.preventDefault();

    const message = input.value.trim();
    if (!message) return;

    addMessage(message, "user");
    input.value = "";
    send.disabled = true;

    const waiting = addMessage("הסוכן עובד, מחפש...", "bot");

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({message})
        });

        const data = await response.json();
        waiting.textContent = data.reply || "לא התקבלה תשובה";

        if (data.items) {
            data.items.forEach(item => {
                const card = document.createElement("div");
                card.className = "card";

                const link = document.createElement("a");
                link.href = item.url;
                link.target = "_blank";
                link.rel = "noopener";
                link.textContent = item.title;

                const price = document.createElement("div");
                price.className = "price";
                price.textContent = item.price;

                card.appendChild(link);
                card.appendChild(price);
                chat.appendChild(card);
            });
        }
    } catch(error) {
        waiting.textContent = "אירעה תקלה. נסה שוב.";
    }

    send.disabled = false;
    chat.scrollTop = chat.scrollHeight;
});
</script>
</body>
</html>
"""


class ChatMessage(BaseModel):
    message: str


def get_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("חשבון המפתחים של eBay עדיין לא חובר")

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        },
        timeout=30
    )

    response.raise_for_status()
    return response.json()["access_token"]


def search_ebay(keyword):
    token = get_token()

    response = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": keyword, "limit": 10},
        timeout=30
    )

    response.raise_for_status()
    return response.json()


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/chat")
def chat(data: ChatMessage):
    keyword = data.message.strip()

    if not CLIENT_ID or not CLIENT_SECRET:
        return {
            "reply": "הצ'אט פעיל! כדי לבצע חיפוש אמיתי צריך לחבר את חשבון המפתחים של eBay."
        }

    try:
        results = search_ebay(keyword)
        items = []

        for item in results.get("itemSummaries", []):
            price = item.get("price", {})

            items.append({
                "title": item.get("title", ""),
                "price": str(price.get("value", "")) + " " + price.get("currency", ""),
                "url": item.get("itemWebUrl", "")
            })

        return {
            "reply": f"מצאתי {len(items)} מוצרים עבורך:",
            "items": items
        }

    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
