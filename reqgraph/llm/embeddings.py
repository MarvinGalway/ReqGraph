"""Embeddings are deferred this pass (Anthropic has no embeddings endpoint;
wiring a separate provider like Voyage AI was explicitly postponed to avoid
a second API key/account for this pass — see implementation plan). This
module ships the interface only. Every candidate-discovery path
(bootstrap-infer grouping, triage-issue, impact) uses deterministic graph
traversal and works correctly with `provider=None`.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider | None:
    """Returns None until a concrete provider is configured — callers must
    handle the no-vector case rather than assuming one is always available.
    """
    return _provider
