"""Configuracion de la aplicacion (Pydantic Settings)."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RISKHUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    env: str = "development"
    secret_key: str = "change-me-in-production-very-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 8 * 60  # 8 horas

    # Base de datos (SQLite por defecto; cambia a postgresql://... si quieres)
    db_path: str = "./riskhub.db"
    database_url: str | None = None

    # Servidor
    host: str = "127.0.0.1"
    port: int = 8000

    # Admin inicial
    admin_email: str = "admin@company.internal"
    admin_password: str = "ChangeMe123!"

    # IA (Claude API - opcional)
    anthropic_api_key: str | None = None

    # OSINT APIs (huella-digital integration)
    hibp_api_key: str | None = None                    # Have I Been Pwned
    virustotal_api_key: str | None = None             # VirusTotal
    leakcheck_api_key: str | None = None              # LeakCheck
    intelx_api_key: str | None = None                 # Intelligence X
    github_api_token: str | None = None               # GitHub

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"


settings = Settings()
