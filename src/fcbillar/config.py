"""Configuració carregada des de .env via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="FCB_",
        extra="ignore",
    )

    user: str = Field(default="", description="Usuari de la intranet de fcbillar.cat")
    password: SecretStr = Field(default=SecretStr(""), description="Contrasenya")

    # La competicio ha marxat a intranet.fcbillar.cat; www ja no serveix.
    base_url: str = "https://intranet.fcbillar.cat"
    request_delay_sec: float = 1.0
    cache_html: bool = True

    db_path: Path = Path("data/fcbillar.db")
    cache_dir: Path = Path("data/cache")

    def model_post_init(self, _ctx) -> None:
        if not self.db_path.is_absolute():
            self.db_path = PROJECT_ROOT / self.db_path
        if not self.cache_dir.is_absolute():
            self.cache_dir = PROJECT_ROOT / self.cache_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_credentials(self) -> bool:
        return bool(self.user and self.password.get_secret_value())


def get_settings() -> Settings:
    return Settings()
