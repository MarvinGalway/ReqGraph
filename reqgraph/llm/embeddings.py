"""Local/offline embeddings via `fastembed` (ONNX-based, no torch, no API
key, no cloud account) — the `embeddings` optional extra. Deliberately not a
cloud provider: Anthropic has no embeddings endpoint, and reopening a
cloud option (e.g. Voyage AI) would reintroduce the "needs a second API
key/account" property that caused this to be deferred twice already.

Every candidate-discovery path in this codebase (bootstrap-infer grouping,
triage-issue, impact) already treats a `None` provider as "fall back to
deterministic graph traversal" — this module ships a real provider now, but
callers still degrade gracefully when the `embeddings` extra isn't
installed, or when a project's Neo4j vector indexes weren't created
(`init --with-vector`).
"""

from __future__ import annotations

from typing import Protocol

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"  # fastembed's default; 384 dims


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbeddingProvider:
    """Wraps `fastembed.TextEmbedding`. Import happens lazily inside
    `__init__` so the base install never requires the `embeddings` extra.
    """

    dimensions = 384

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        from fastembed import TextEmbedding  # intentionally lazy import, see class docstring

        self._model = TextEmbedding(model_name=model_name)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [vector.tolist() for vector in self._model.embed(texts)]


_provider: EmbeddingProvider | None = None
_resolved = False


def get_embedding_provider() -> EmbeddingProvider | None:
    """Lazily instantiates a `LocalEmbeddingProvider`, caching the result
    (including the "unavailable" result) for the process lifetime. Returns
    None if the `embeddings` extra isn't installed — callers must handle
    this rather than assuming a provider is always available.
    """
    global _provider, _resolved
    if not _resolved:
        try:
            _provider = LocalEmbeddingProvider()
        except ImportError:
            _provider = None
        _resolved = True
    return _provider


def reset_embedding_provider_cache() -> None:
    """Test helper — forces get_embedding_provider() to re-resolve."""
    global _provider, _resolved
    _provider = None
    _resolved = False
