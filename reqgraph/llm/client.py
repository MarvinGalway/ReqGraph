"""Anthropic/OpenAI client singletons, one per provider actually used.

Each role picks its provider independently (`reqgraph.llm.roles.resolve_provider`),
so more than one client can be live in the same process — hence a cache keyed by
provider name rather than a single `_client` global.
"""

from __future__ import annotations

from typing import Any

import anthropic

from reqgraph.config import get_settings

_clients: dict[str, Any] = {}


def get_client(provider: str = "anthropic") -> Any:
    if provider not in _clients:
        settings = get_settings()
        if provider == "anthropic":
            if not settings.anthropic_api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set — required for roles bound to the "
                    "'anthropic' provider (run-critic, formalize, derive-tasks, "
                    "bootstrap-infer, impact, triage-issue)."
                )
            _clients[provider] = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        elif provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set — required for roles bound to the "
                    "'openai' provider (set REQGRAPH_PROVIDER=openai or "
                    "REQGRAPH_PROVIDER_<ROLE>=openai). Also requires the `llm-openai` "
                    "extra: pip install -e '.[llm-openai]'."
                )
            import openai  # lazy: optional dependency, only needed for this provider

            _clients[provider] = openai.OpenAI(api_key=settings.openai_api_key)
        else:
            raise RuntimeError(f"Unknown LLM provider {provider!r} (supported: anthropic, openai)")
    return _clients[provider]


def reset_client_cache() -> None:
    global _clients
    _clients = {}
