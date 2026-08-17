"""One function per edge type in graph-schema-v0.2.json's `edges` block.

This module is the sole choke point for writing relationships into the
graph — combined with the per-label node repositories (also under
`graph/repositories/`), every graph mutation in this codebase traces back to
one of these ~20 functions or a `NodeRepository.create/update_fields` call.
That is what makes "graph-cli is the only write path to Neo4j" auditable.
"""

from __future__ import annotations

from typing import Any

from neo4j import Session


def _create_edge(sess: Session, edge_type: str, from_id: str, to_id: str, **props: Any) -> None:
    query = (
        f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
        f"CREATE (a)-[r:{edge_type} $props]->(b)"
    )
    sess.run(query, from_id=from_id, to_id=to_id, props=props)


def clarifies(sess: Session, from_id: str, to_id: str) -> None:
    """Clarification|Assumption -[:CLARIFIES]-> Requirement"""
    _create_edge(sess, "CLARIFIES", from_id, to_id)


def formalizes(
    sess: Session,
    from_id: str,
    to_id: str,
    *,
    knowledge_status: str = "generated",
    assumptions: list[str] | None = None,
    generated_by: str = "human",
    reviewed_by: str | None = None,
) -> None:
    """Contract -[:FORMALIZES]-> Requirement"""
    props: dict[str, Any] = {
        "knowledge_status": knowledge_status,
        "assumptions": assumptions or [],
        "generated_by": generated_by,
    }
    if reviewed_by is not None:
        props["reviewed_by"] = reviewed_by
    _create_edge(sess, "FORMALIZES", from_id, to_id, **props)


def witnesses(sess: Session, from_id: str, to_id: str) -> None:
    """Example -[:WITNESSES]-> Contract"""
    _create_edge(sess, "WITNESSES", from_id, to_id)


def derives_from(sess: Session, from_id: str, to_id: str) -> None:
    """Task -[:DERIVES_FROM]-> Contract"""
    _create_edge(sess, "DERIVES_FROM", from_id, to_id)


def generated_by(sess: Session, from_id: str, to_id: str) -> None:
    """CodeUnit|ConfigUnit|Test -[:GENERATED_BY]-> Task"""
    _create_edge(sess, "GENERATED_BY", from_id, to_id)


def generated_from(sess: Session, from_id: str, to_id: str) -> None:
    """Test -[:GENERATED_FROM]-> Example"""
    _create_edge(sess, "GENERATED_FROM", from_id, to_id)


def implements(sess: Session, from_id: str, to_id: str) -> None:
    """CodeUnit -[:IMPLEMENTS]-> Contract"""
    _create_edge(sess, "IMPLEMENTS", from_id, to_id)


def constrains(sess: Session, from_id: str, to_id: str) -> None:
    """ConfigUnit -[:CONSTRAINS]-> Contract"""
    _create_edge(sess, "CONSTRAINS", from_id, to_id)


def tests(sess: Session, from_id: str, to_id: str) -> None:
    """Test -[:TESTS]-> Contract|CodeUnit|ConfigUnit"""
    _create_edge(sess, "TESTS", from_id, to_id)


def depends_on(sess: Session, from_id: str, to_id: str, *, kind: str = "inferred") -> None:
    """Task|CodeUnit|ConfigUnit -[:DEPENDS_ON]-> Task|CodeUnit|ConfigUnit"""
    _create_edge(sess, "DEPENDS_ON", from_id, to_id, kind=kind)


def contradicts(
    sess: Session, from_id: str, to_id: str, *, status: str = "open", resolution: str | None = None
) -> None:
    """Requirement|Contract -[:CONTRADICTS]-> Requirement|Contract"""
    props: dict[str, Any] = {"status": status}
    if resolution is not None:
        props["resolution"] = resolution
    _create_edge(sess, "CONTRADICTS", from_id, to_id, **props)


def refines(sess: Session, from_id: str, to_id: str) -> None:
    """Contract -[:REFINES]-> Contract"""
    _create_edge(sess, "REFINES", from_id, to_id)


def supersedes(sess: Session, from_id: str, to_id: str) -> None:
    """Requirement|Contract|CodeUnit|ConfigUnit -[:SUPERSEDES]-> (same label, prior version)"""
    _create_edge(sess, "SUPERSEDES", from_id, to_id)


def evidences(sess: Session, from_id: str, to_id: str) -> None:
    """Test|CodeUnit|ConfigUnit -[:EVIDENCES]-> ObservedBehavior"""
    _create_edge(sess, "EVIDENCES", from_id, to_id)


def supports(sess: Session, from_id: str, to_id: str) -> None:
    """ObservedBehavior -[:SUPPORTS]-> Contract"""
    _create_edge(sess, "SUPPORTS", from_id, to_id)


def inferred_from(sess: Session, from_id: str, to_id: str) -> None:
    """Requirement|Contract|Example -[:INFERRED_FROM]-> ObservedBehavior|Test|CodeUnit|ConfigUnit"""
    _create_edge(sess, "INFERRED_FROM", from_id, to_id)


def found_during(sess: Session, from_id: str, to_id: str) -> None:
    """Issue -[:FOUND_DURING]-> Task"""
    _create_edge(sess, "FOUND_DURING", from_id, to_id)


def affects(sess: Session, from_id: str, to_id: str) -> None:
    """Issue -[:AFFECTS]-> CodeUnit|ConfigUnit"""
    _create_edge(sess, "AFFECTS", from_id, to_id)


def violates(sess: Session, from_id: str, to_id: str) -> None:
    """Issue -[:VIOLATES]-> Contract"""
    _create_edge(sess, "VIOLATES", from_id, to_id)


def explained_by(sess: Session, from_id: str, to_id: str) -> None:
    """Issue -[:EXPLAINED_BY]-> Contract"""
    _create_edge(sess, "EXPLAINED_BY", from_id, to_id)


def blocks(sess: Session, from_id: str, to_id: str) -> None:
    """Issue -[:BLOCKS]-> Task"""
    _create_edge(sess, "BLOCKS", from_id, to_id)


def addresses(sess: Session, from_id: str, to_id: str) -> None:
    """Task -[:ADDRESSES]-> Issue"""
    _create_edge(sess, "ADDRESSES", from_id, to_id)


# ---------------------------------------------------------------------------
# Generic traversal helpers (read-only) shared by context/impact/consistency
# ---------------------------------------------------------------------------


def outgoing_ids(sess: Session, node_id: str, edge_type: str) -> list[str]:
    result = sess.run(
        f"MATCH (a {{id: $id}})-[:{edge_type}]->(b) RETURN b.id AS id", id=node_id
    )
    return [r["id"] for r in result]


def incoming_ids(sess: Session, node_id: str, edge_type: str) -> list[str]:
    result = sess.run(
        f"MATCH (a {{id: $id}})<-[:{edge_type}]-(b) RETURN b.id AS id", id=node_id
    )
    return [r["id"] for r in result]


def edge_exists(sess: Session, edge_type: str, from_id: str, to_id: str) -> bool:
    result = sess.run(
        f"MATCH (a {{id: $from_id}})-[:{edge_type}]->(b {{id: $to_id}}) RETURN count(*) AS c",
        from_id=from_id,
        to_id=to_id,
    )
    record = result.single()
    return bool(record and record["c"] > 0)
