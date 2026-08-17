"""`impact <codeunit|configunit>` deterministic candidate assembly, per
models-config-v0.2.json's `impact_traversal_rules`. Vector-similarity
candidate discovery is skipped this pass (embeddings deferred) — see
`llm/embeddings.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from neo4j import Session

from reqgraph.graph.models import Contract, Issue, Test
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import contracts, issues, tests

OPEN_ISSUE_STATUSES = {"open", "triaging", "ready", "in_progress"}


@dataclass
class ImpactCandidates:
    target_id: str
    target_label: str
    contracts: list[Contract] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    dependent_ids: list[str] = field(default_factory=list)
    open_issues: list[Issue] = field(default_factory=list)


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


def gather(
    sess: Session, target_id: str, target_label: str, depth: int = 2
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

    return ImpactCandidates(
        target_id=target_id,
        target_label=target_label,
        contracts=contract_list,
        tests=test_list,
        dependent_ids=dependent_ids,
        open_issues=issue_list,
    )
