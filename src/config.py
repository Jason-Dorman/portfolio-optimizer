"""Application-wide settings loaded from environment / .env file."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Schwab OAuth — optional at load time; validated at call time by the auth adapter
    schwab_client_id: Optional[str] = None
    schwab_client_secret: Optional[str] = None
    schwab_callback_url: str = "https://127.0.0.1:5000/callback"

    # FRED — optional at load time; validated at call time by the FRED adapter
    fred_api_key: Optional[str] = None

    # App — port 5000 to match Schwab callback URL
    app_host: str = "127.0.0.1"
    app_port: int = 5000

    # SSL certificates
    ssl_cert_dir: Path = Path("certs")

    @property
    def ssl_cert_file(self) -> Path:
        return self.ssl_cert_dir / "localhost.crt"

    @property
    def ssl_key_file(self) -> Path:
        return self.ssl_cert_dir / "localhost.key"

    @property
    def base_url(self) -> str:
        return f"https://{self.app_host}:{self.app_port}"


settings = Settings()
