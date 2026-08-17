from __future__ import annotations

import pytest

from reqgraph.graph.models import Contract, Issue
from reqgraph.graph.repositories.contract import ContractRepository
from reqgraph.graph.repositories.issue import IssueRepository
from reqgraph.graph.schema import apply_schema
from reqgraph.graph.vector_search import vector_search
from reqgraph.llm.embeddings import get_embedding_provider

pytestmark = pytest.mark.integration


def test_vector_search_ranks_the_actually_similar_contract_first(neo4j_session):
    apply_schema(neo4j_session, with_vector=True)
    repo = ContractRepository()

    orders = Contract(preconditions=["order exists"], postconditions=["order is cancelled unless already shipped"])
    payments = Contract(preconditions=["payment exists"], postconditions=["payment is refunded to the original method"])
    weather = Contract(preconditions=["forecast exists"], postconditions=["forecast shows sunny skies in Paris"])
    for c in (orders, payments, weather):
        repo.create(neo4j_session, c)
        assert c.embedding is not None  # confirms the _embedding_text hook actually fired

    provider = get_embedding_provider()
    assert provider is not None
    query_vector = provider.embed("cancelling an order that hasn't shipped yet")

    results = vector_search(neo4j_session, "Contract", query_vector, k=3)
    assert results
    top_id, _score = results[0]
    assert top_id == orders.id


def test_vector_search_excludes_given_id(neo4j_session):
    apply_schema(neo4j_session, with_vector=True)
    repo = IssueRepository()
    issue_a = Issue(title="Refund flow double-charges customers")
    issue_b = Issue(title="Double refund possible on race condition")
    for i in (issue_a, issue_b):
        repo.create(neo4j_session, i)

    provider = get_embedding_provider()
    assert provider is not None
    query_vector = provider.embed(issue_a.title)

    results = vector_search(neo4j_session, "Issue", query_vector, k=5, exclude_id=issue_a.id)
    result_ids = [r[0] for r in results]
    assert issue_a.id not in result_ids
    assert issue_b.id in result_ids


def test_vector_search_returns_empty_for_non_vector_eligible_label(neo4j_session):
    apply_schema(neo4j_session, with_vector=True)
    assert vector_search(neo4j_session, "Task", [0.0] * 384, k=5) == []
