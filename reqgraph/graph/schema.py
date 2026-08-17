"""Schema DDL: per-label uniqueness constraints and (optional) vector indexes.

Vector indexes are opt-in (`with_vector=True`) because embeddings are
deferred in this pass — see `reqgraph/llm/embeddings.py`. Without them the
system runs on deterministic graph traversal only.
"""

from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import NODE_LABELS

# Nodes eligible for a vector index on `.embedding`, per
# models-config-v0.2.json -> retrieval.vector_index.nodes
VECTOR_INDEX_LABELS = ("Requirement", "Contract", "Example", "ObservedBehavior", "Issue")

DEFAULT_EMBEDDING_DIMENSIONS = 1024
DEFAULT_SIMILARITY_FUNCTION = "cosine"


def constraint_statements() -> list[str]:
    return [
        f"CREATE CONSTRAINT {label.lower()}_id_unique IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        for label in NODE_LABELS
    ] + [
        "CREATE INDEX task_external_id IF NOT EXISTS FOR (t:Task) ON (t.external_id)",
    ]


def vector_index_statements(
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    similarity_function: str = DEFAULT_SIMILARITY_FUNCTION,
) -> list[str]:
    statements = []
    for label in VECTOR_INDEX_LABELS:
        index_name = f"{label.lower()}_embedding_vector"
        statements.append(
            f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
            f"FOR (n:{label}) ON (n.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dimensions, "
            "`vector.similarity_function`: $similarity_function}}"
        )
    return statements


def apply_schema(sess: Session, with_vector: bool = False) -> list[str]:
    """Applies constraints (always) and vector indexes (opt-in). Returns applied statement names."""
    applied: list[str] = []
    for stmt in constraint_statements():
        sess.run(stmt)
        applied.append(stmt)
    if with_vector:
        for stmt in vector_index_statements():
            sess.run(
                stmt,
                dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
                similarity_function=DEFAULT_SIMILARITY_FUNCTION,
            )
            applied.append(stmt)
    return applied
