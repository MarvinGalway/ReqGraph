from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import CodeUnit
from reqgraph.graph.repositories.base import NodeRepository, from_neo4j_properties
from reqgraph.graph.repositories.edges import implements, supersedes


class CodeUnitRepository(NodeRepository[CodeUnit]):
    label = "CodeUnit"
    model_cls = CodeUnit

    def find_current(self, sess: Session, path: str, symbol: str) -> CodeUnit | None:
        """Latest (non-superseded) CodeUnit at this path+symbol, if any.

        Used by `bootstrap-scan`/`detect-changes` to decide whether a symbol
        is new, unchanged, or hash-changed.
        """
        result = sess.run(
            """
            MATCH (n:CodeUnit {path: $path, symbol: $symbol})
            WHERE NOT EXISTS { MATCH (:CodeUnit)-[:SUPERSEDES]->(n) }
            RETURN n
            ORDER BY n.created_at DESC
            LIMIT 1
            """,
            path=path,
            symbol=symbol,
        )
        record = result.single()
        if record is None:
            return None
        return from_neo4j_properties(dict(record["n"]), self.model_cls)

    def create_version(
        self, sess: Session, new_unit: CodeUnit, supersedes_id: str, carry_forward_implements: bool = True
    ) -> CodeUnit:
        """Writes a new CodeUnit version, links -[:SUPERSEDES]-> the prior one, and by
        default copies forward its IMPLEMENTS edges (spec §9.2: a technical
        change does not automatically invalidate the Contract link — that is
        `impact`'s job, not `detect-changes`'s).
        """
        self.create(sess, new_unit)
        supersedes(sess, new_unit.id, supersedes_id)
        if carry_forward_implements:
            result = sess.run(
                "MATCH (:CodeUnit {id: $old_id})-[:IMPLEMENTS]->(c:Contract) RETURN c.id AS id",
                old_id=supersedes_id,
            )
            for record in result:
                implements(sess, new_unit.id, record["id"])
        return new_unit
