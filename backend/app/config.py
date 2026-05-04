from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://scilibrarian:changeme@localhost:5432/scilibrarian"
    secret_key: str = "dev-secret-key"
    access_token_expire_minutes: int = 1440
    anthropic_api_key: str = ""
    environment: str = "development"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
