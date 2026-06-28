from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx

from app.core.config import settings
from app.services.auth_service import get_current_user
from app.services.gemini_throttle import (
    _GeminiRateLimited,
    gemini_throttle,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    messages: list[dict]
    context: dict | None = None


class ChatResponse(BaseModel):
    reply: str


def _gemini_url() -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
    )


def _cache_key_for(messages: list[dict]) -> str:
    """Hash of the last user message. Chat isn't cache-friendly (most messages
    are unique) but identical retries within the TTL will short-circuit."""
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    return gemini_throttle.make_key("ai.chat", last_user[:500])


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    if not settings.gemini_api_key:
        raise HTTPException(status_code=501, detail="AI not configured: GEMINI_API_KEY not set")

    cache_key = _cache_key_for(req.messages)

    def _do_call() -> str | None:
        contents = []
        for msg in req.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        system = (
            "You are a helpful kitchen assistant. You help with meal planning, "
            "nutritional info, recipe suggestions, and food storage advice. "
            "Be concise and practical."
        )

        with httpx.Client(timeout=15) as client:
            resp = client.post(
                _gemini_url(),
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": contents,
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800},
                },
            )
        if resp.status_code == 429:
            raise _GeminiRateLimited(f"HTTP 429: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError):
            return None

    reply = gemini_throttle.acquire_and_call(cache_key, "ai.chat", _do_call)
    if reply is None:
        # All paths that return None: missing key (already raised above),
        # throttled/cooldown, 429, parse error, generic exception. We can't
        # tell them apart from here, but a 503 is more honest than 502 for
        # throttling vs parse error.
        stats = gemini_throttle.stats()
        if stats["in_cooldown_now"]:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"AI temporarily unavailable (rate-limit cooldown, "
                    f"{int(stats['cooldown_remaining_s'])}s remaining). Try again later."
                ),
            )
        raise HTTPException(status_code=502, detail="AI response error")

    return ChatResponse(reply=reply)


@router.get("/stats")
def ai_stats(current_user: dict = Depends(get_current_user)):
    """Observability endpoint for the throttler. Returns counters and current
    cooldown state. Useful for debugging without dumping uvicorn logs."""
    return gemini_throttle.stats()
