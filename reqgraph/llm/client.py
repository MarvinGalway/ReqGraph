"""Anthropic client singleton."""

from __future__ import annotations

import anthropic

from reqgraph.config import get_settings

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set — required for LLM-backed commands "
                "(run-critic, formalize, derive-tasks, bootstrap-infer, impact, triage-issue)."
            )
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def reset_client_cache() -> None:
    global _client
    _client = None
