"""`impact <codeunit|configunit>` candidate assembly, per
models-config-v0.2.json's `impact_traversal_rules`. Deterministic graph
traversal is the primary (and only required) candidate source; vector
similarity is an optional additional source when the `embeddings` extra is
installed and the project's Neo4j vector indexes exist (`init
--with-vector`) — per the original retrieval design, it only ever *proposes*
extra candidates, never shrinks the deterministic set or authorizes
anything on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from neo4j import Session

from reqgraph.graph.models import Contract, Issue, Test
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import contracts, issues, tests
from reqgraph.graph.vector_search import vector_search
from reqgraph.llm.embeddings import get_embedding_provider

OPEN_ISSUE_STATUSES = {"open", "triaging", "ready", "in_progress"}


@dataclass
class ImpactCandidates:
    target_id: str
    target_label: str
    contracts: list[Contract] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    dependent_ids: list[str] = field(default_factory=list)
    open_issues: list[Issue] = field(default_factory=list)
    vector_candidate_contracts: list[Contract] = field(default_factory=list)


def _bounded_depends_on(sess: Session, node_id: str, depth: int) -> list[str]:
    result = sess.run(
        f"""
        MATCH (n {{id: $id}})
        MATCH (n)-[:DEPENDS_ON*1..{depth}]-(d)
        WHERE d.id <> $id
        RETURN DISTINCT d.id AS id
        """,
        id=node_id,
    )
    return [r["id"] for r in result]


def _vector_candidate_contracts(
    sess: Session, query_text: str | None, exclude_ids: set[str], k: int = 5
) -> list[Contract]:
    if not query_text:
        return []
    provider = get_embedding_provider()
    if provider is None:
        return []
    query_vector = provider.embed(query_text)
    found = []
    for contract_id, _score in vector_search(sess, "Contract", query_vector, k=k):
        if contract_id in exclude_ids:
            continue
        contract = contracts.get(sess, contract_id)
        if contract:
            found.append(contract)
    return found


def gather(
    sess: Session,
    target_id: str,
    target_label: str,
    depth: int = 2,
    embedding_query_text: str | None = None,
) -> ImpactCandidates:
    contract_edge = "IMPLEMENTS" if target_label == "CodeUnit" else "CONSTRAINS"
    contract_ids = edges.outgoing_ids(sess, target_id, contract_edge)
    contract_list = [c for c in (contracts.get(sess, cid) for cid in contract_ids) if c]

    test_ids = edges.incoming_ids(sess, target_id, "TESTS")
    test_list = [t for t in (tests.get(sess, tid) for tid in test_ids) if t]

    dependent_ids = _bounded_depends_on(sess, target_id, depth)

    issue_ids = edges.incoming_ids(sess, target_id, "AFFECTS")
    issue_list = [
        i
        for i in (issues.get(sess, iid) for iid in issue_ids)
        if i and i.workflow_status in OPEN_ISSUE_STATUSES
    ]

    vector_candidates = _vector_candidate_contracts(
        sess, embedding_query_text, exclude_ids={c.id for c in contract_list}
    )

    return ImpactCandidates(
        target_id=target_id,
        target_label=target_label,
        contracts=contract_list,
        tests=test_list,
        dependent_ids=dependent_ids,
        open_issues=issue_list,
        vector_candidate_contracts=vector_candidates,
    )
