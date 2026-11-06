import os
import base64
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI(title="eBay AI Agent")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")
EBAY_ENVIRONMENT = os.getenv("EBAY_ENVIRONMENT", "production")

BASE_URL = (
    "https://api.ebay.com"
    if EBAY_ENVIRONMENT == "production"
    else "https://api.sandbox.ebay.com"
)

scheduler = BackgroundScheduler(timezone="Asia/Jerusalem")


def get_ebay_token():
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        raise ValueError("Missing eBay API credentials")

    credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        f"{BASE_URL}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=30,
    )

    response.raise_for_status()
    return response.json()["access_token"]


def search_products(keyword="popular products"):
    token = get_ebay_token()

    response = requests.get(
        f"{BASE_URL}/buy/browse/v1/item_summary/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": keyword, "limit": 10},
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def daily_scan():
    print("Starting daily eBay scan:", datetime.now(ZoneInfo("Asia/Jerusalem")))
    try:
        search_products()
        print("Daily scan completed")
    except Exception as error:
        print("Daily scan failed:", error)


@app.on_event("startup")
def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            daily_scan,
            "cron",
            hour=8,
            minute=0,
            id="daily_ebay_scan",
            replace_existing=True,
        )
        scheduler.start()


@app.on_event("shutdown")
def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()


@app.get("/")
def home():
    return {"status": "running", "agent": "eBay AI Agent"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/search")
def search(keyword: str):
    try:
        return search_products(keyword)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
