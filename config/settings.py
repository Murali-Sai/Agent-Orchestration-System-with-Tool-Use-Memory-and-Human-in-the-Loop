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

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # Thresholds
    confidence_threshold: float = 0.6
    quality_threshold: float = 0.65
    max_retries: int = 2

    # Async dispatch — only enable when a Celery worker is actually running
    # (e.g. docker-compose). Without a worker, jobs enqueue to Redis but never
    # run, so this MUST stay False on hosts with Redis but no worker (Render free).
    use_celery: bool = False

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    api_port: int = 8000
    ui_port: int = 8501
    cors_origins: str = "*"   # comma-separated; "*" for dev, restrict for prod

    # Models
    primary_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
