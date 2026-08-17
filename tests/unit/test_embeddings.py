from __future__ import annotations

import math

from reqgraph.llm.embeddings import LocalEmbeddingProvider


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def test_embed_returns_vector_of_expected_dimensionality():
    provider = LocalEmbeddingProvider()
    vector = provider.embed("cancel an order")
    assert len(vector) == provider.dimensions == 384
    assert all(isinstance(x, float) for x in vector)


def test_embed_batch_matches_individual_embed_calls():
    provider = LocalEmbeddingProvider()
    texts = ["cancel an order", "refund a payment"]
    batch = provider.embed_batch(texts)
    assert len(batch) == 2
    assert len(batch[0]) == 384


def test_similar_texts_are_closer_than_dissimilar_ones():
    provider = LocalEmbeddingProvider()
    order_a = provider.embed("Users can cancel an order unless it has already shipped.")
    order_b = provider.embed("Cancelling an order is not allowed once it ships.")
    unrelated = provider.embed("The weather in Paris is sunny today.")

    sim_related = _cosine(order_a, order_b)
    sim_unrelated = _cosine(order_a, unrelated)
    assert sim_related > sim_unrelated


def test_embed_batch_empty_list_returns_empty():
    provider = LocalEmbeddingProvider()
    assert provider.embed_batch([]) == []
