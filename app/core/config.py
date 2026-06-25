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

    class Config:
        env_file = ".env"


settings = Settings()
