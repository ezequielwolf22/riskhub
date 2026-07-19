"""Configuracion de la aplicacion (Pydantic Settings)."""
from pathlib import Path
from pydantic import Field, field_validator
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
    secret_key: str = Field(..., description="Secret key for JWT and Fernet encryption. MUST be 32+ chars.")
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60           # access token (se renueva via refresh)
    jwt_refresh_expires_minutes: int = 12 * 60  # refresh token: sesion maxima 12h

    # Base de datos (SQLite por defecto; cambia a postgresql://... si quieres)
    db_path: str = "./riskhub.db"
    database_url: str | None = None

    # Servidor
    host: str = "127.0.0.1"
    port: int = 8000

    # URL publica de la aplicacion — usada en emails de reset de contrasena.
    # Si no se configura, el endpoint forgot-password devolvera 503.
    public_url: str = ""

    # Admin inicial (SECURITY: must be configured in .env, no defaults)
    admin_email: str = Field(..., description="Initial admin email. MUST be configured in .env")
    admin_password: str = Field(..., description="Initial admin password. MUST be configured in .env")

    # IA (Claude API - opcional)
    anthropic_api_key: str | None = None

    # OSINT APIs (huella-digital integration)
    hibp_api_key: str | None = None                    # Have I Been Pwned
    virustotal_api_key: str | None = None             # VirusTotal
    leakcheck_api_key: str | None = None              # LeakCheck
    intelx_api_key: str | None = None                 # Intelligence X
    github_api_token: str | None = None               # GitHub

    @field_validator('secret_key', mode='after')
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("RISKHUB_SECRET_KEY debe tener al menos 32 caracteres. Genera uno con: python -c \"import secrets; print(secrets.token_urlsafe(64))\"")
        return v

    @field_validator('admin_password', mode='after')
    def validate_admin_password(cls, v):
        if len(v) < 8:
            raise ValueError("RISKHUB_ADMIN_PASSWORD debe tener al menos 8 caracteres")
        return v

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"


settings = Settings()
