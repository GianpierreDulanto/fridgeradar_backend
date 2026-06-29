from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Fridge Inventory API"
    database_url: str = "postgresql+psycopg://postgres:bd123@localhost:5432/fridge_inventory"
    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 7
    environment: str = "local"
    gemini_api_key: str = ""

    # Gemini model selection. Some free-tier keys don't have access to
    # `gemini-2.0-flash` (returns 422). If the primary model returns 422
    # the service falls back to `gemini_fallback_model`. If both fail, the
    # request returns FALLBACK_RECIPES (for /api/recipes/suggest) or 503
    # (for /api/ai/chat).
    gemini_model: str = "gemini-2.0-flash"
    gemini_fallback_model: str = "gemini-1.5-flash"

    # Gemini throttle tunables. Default values match the free-tier quotas
    # (15 RPM, 1500 RPD). Override in `.env` for development or for paid
    # keys with higher limits.
    gemini_min_interval_s: float = 4.0          # min seconds between calls
    gemini_cooldown_base_s: float = 60.0        # first 429 -> 60s cooldown
    gemini_cooldown_max_s: float = 3600.0        # cap exponential backoff at 1h
    gemini_cache_ttl_s: float = 300.0           # success -> cache 5 min
    gemini_cache_neg_ttl_s: float = 30.0        # failure -> cache 30s

    class Config:
        env_file = ".env"


settings = Settings()
