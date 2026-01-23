from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "Solo RPG Platform"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/solo_rpg"

    # Claude API
    anthropic_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # GM AI settings (used during gameplay sessions)
    gm_provider: str = "openai"  # Default to OpenAI to avoid Claude credit issues
    gm_claude_model: str = "claude-sonnet-4-20250514"
    gm_openai_model: str = "gpt-4o-mini"

    # Processing AI settings (used for parsing adventures, generating descriptions)
    processing_provider: str = "openai"
    processing_claude_model: str = "claude-haiku-4-5-20250101"
    processing_openai_model: str = "gpt-4o-mini"

    # PDF Storage
    pdf_storage_path: str = "/home/orochford/rpgs"

    # Markdown export storage (for LLM context loading)
    markdown_storage_path: str = "/home/orochford/rpgs/markdown"

    # RAG Settings
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: str = "text-embedding-3-small"
    top_k_chunks: int = 7

    # WebSocket
    ws_ping_interval: int = 25
    ws_ping_timeout: int = 120

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
