from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

class Settings(BaseSettings):
    # Environment
    environment: Literal["development", "testing", "staging", "production"] = "development"

    # MLflow
    mlflow_tracking_uri: str
    mlflow_experiment: str
    mlflow_trace_timeout_seconds: Optional[int] = None

    # LLM API Keys
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    #Web Search API Keys
    tavily_api_key: Optional[str] = None

    # LangSmith
    langsmith_api_key: Optional[str] = None
    langsmith_tracing: bool = False
    langsmith_project: Optional[str] = None
    langsmith_endpoint: Optional[str] = None

    # Local LLM name, e.g. "qwen-7b-chat" or "gemini-1.5-pro"
    local_llm: str

    # Database path
    db_path: Path = Path(__file__).parent.parent / "state_db" / "long-running-job.db"

    # CORS — comma-separated or JSON array, e.g. CORS_ORIGINS='["http://host1","http://host2"]'
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings() # type: ignore
