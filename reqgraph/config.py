"""Runtime configuration for reqgraph, sourced from env vars / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "reqgraph-dev"
    neo4j_database: str = "neo4j"

    anthropic_api_key: str | None = None

    reqgraph_project_root: Path = Path(".")

    def project_state_dir(self) -> Path:
        return self.reqgraph_project_root / ".project-state"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Test helper — forces get_settings() to re-read the environment."""
    global _settings
    _settings = None
