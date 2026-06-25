from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from app.core.config import settings

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    messages: list[dict]
    context: dict | None = None


class ChatResponse(BaseModel):
    reply: str


GEMINI_API_KEY = settings.gemini_api_key
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(req: ChatRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=501, detail="AI not configured: GEMINI_API_KEY not set")

    contents = []
    for msg in req.messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    system = "You are a helpful kitchen assistant. You help with meal planning, nutritional info, recipe suggestions, and food storage advice. Be concise and practical."

    async with httpx.AsyncClient() as client:
        resp = await client.post(GEMINI_URL, json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 800,
            }
        })
        data = resp.json()

    try:
        reply = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="AI response error")

    return ChatResponse(reply=reply)
