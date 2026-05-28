from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    tavily_api_key: str = ""

    # Infrastructure
    redis_url: str = "redis://localhost:6379/0"
    chroma_persist_dir: str = "./chroma_db"

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # Thresholds
    confidence_threshold: float = 0.6
    quality_threshold: float = 0.65
    max_retries: int = 2

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    api_port: int = 8000
    ui_port: int = 8501

    # Models
    primary_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
