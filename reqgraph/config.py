"""Runtime configuration for reqgraph, sourced from env vars / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Loads ReqGraph's own .env first (as base defaults), then a .env in the
    # current working directory if one exists — later files override earlier
    # ones. This lets `graph-cli` run from inside a bootstrapped project's
    # own directory pick up that project's own NEO4J_URI/NEO4J_PASSWORD
    # (pointing at its own dedicated Neo4j instance, per README's isolation
    # guidance) instead of silently falling back to ReqGraph's. Without this,
    # running any command from a project directory looked like it respected
    # that project's .env but actually ignored it — the kind of silent
    # cross-project misconfiguration that once wiped a real project's graph.
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", Path(".env")), env_file_encoding="utf-8", extra="ignore"
    )

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
