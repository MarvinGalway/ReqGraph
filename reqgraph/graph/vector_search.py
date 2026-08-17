"""Vector similarity search over the optional Neo4j vector indexes
(`init --with-vector`, `graph/schema.py::VECTOR_INDEX_LABELS`). Used by
`impact` and `triage-issue` as an additional, optional candidate-discovery
source — per the original retrieval design, vector similarity only ever
*proposes* candidates; it never creates invalidations or authorizes
anything on its own.
"""

from __future__ import annotations

from neo4j import Session

from reqgraph.graph.schema import VECTOR_INDEX_LABELS


def _index_name(label: str) -> str:
    return f"{label.lower()}_embedding_vector"


def vector_search(
    sess: Session, label: str, query_embedding: list[float], k: int = 5, exclude_id: str | None = None
) -> list[tuple[str, float]]:
    """Returns up to `k` (node_id, similarity_score) pairs for `label`,
    most similar first. Returns [] if the label isn't vector-eligible or its
    index doesn't exist (e.g. `init` ran without `--with-vector`) — never
    raises, matching every other "vector search is optional" fallback in
    this codebase.
    """
    if label not in VECTOR_INDEX_LABELS:
        return []
    try:
        result = sess.run(
            f"CALL db.index.vector.queryNodes('{_index_name(label)}', $k, $embedding) "
            "YIELD node, score RETURN node.id AS id, score",
            k=k + (1 if exclude_id else 0),
            embedding=query_embedding,
        )
        pairs = [(record["id"], record["score"]) for record in result]
    except Exception:  # noqa: BLE001 — missing index, wrong dimensions, etc. all degrade to "no candidates"
        return []
    if exclude_id:
        pairs = [p for p in pairs if p[0] != exclude_id]
    return pairs[:k]
