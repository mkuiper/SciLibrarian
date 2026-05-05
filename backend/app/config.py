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
    default_librarian_model: str = "ollama/gemma4:latest"
    default_ingestion_model: str = "ollama/gemma4:latest"

    environment: str = "development"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 50

    # OpenAlex contact email (increases rate limit from 10→unlimited req/s)
    openalex_email: str = ""

    # Semantic Scholar API key (optional, increases rate limit)
    semantic_scholar_api_key: str = ""

    # Email / SMTP (for digest mailing list and reply confirmations)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "alexandria@scilibrarian.local"
    smtp_tls: bool = True

    # IMAP email ingestion — users email PDFs/URLs to Alexandria
    # Alexandria checks this inbox and ingests attachments/links automatically.
    # Use a dedicated mailbox (e.g. ingest@yourdomain.com or a Gmail alias).
    ingest_email_enabled: bool = False
    ingest_imap_host: str = ""
    ingest_imap_port: int = 993
    ingest_imap_username: str = ""
    ingest_imap_password: str = ""
    ingest_imap_folder: str = "INBOX"
    ingest_imap_ssl: bool = True
    ingest_default_project_id: int = 1
    ingest_check_interval_minutes: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
