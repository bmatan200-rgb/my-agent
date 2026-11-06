import os
import base64
import requests
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="eBay AI Agent")

CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AGENT_ACCESS_TOKEN = os.getenv("AGENT_ACCESS_TOKEN", "")
OPENAI_MODEL = "gpt-5.5"
