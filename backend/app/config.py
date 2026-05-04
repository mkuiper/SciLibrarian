from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://scilibrarian:changeme@localhost:5432/scilibrarian"
    secret_key: str = "dev-secret-key"
    access_token_expire_minutes: int = 1440

    # Anthropic (Claude)
    anthropic_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Google Gemini
    gemini_api_key: str = ""
    google_api_key: str = ""

    # Ollama (local models — no key needed)
    ollama_base_url: str = "http://localhost:11434"

    # vLLM (OpenAI-compatible local serving — no key needed)
    vllm_base_url: str = ""

    # Defaults
    default_librarian_model: str = "claude-sonnet-4-6"
    default_ingestion_model: str = "claude-sonnet-4-6"

    environment: str = "development"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 50

    # OpenAlex contact email (increases rate limit from 10→unlimited req/s)
    openalex_email: str = ""

    # Semantic Scholar API key (optional, increases rate limit)
    semantic_scholar_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
