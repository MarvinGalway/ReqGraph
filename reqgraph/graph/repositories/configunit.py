from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import ConfigUnit
from reqgraph.graph.repositories.base import NodeRepository, from_neo4j_properties
from reqgraph.graph.repositories.edges import constrains, supersedes


class ConfigUnitRepository(NodeRepository[ConfigUnit]):
    label = "ConfigUnit"
    model_cls = ConfigUnit

    def find_current(self, sess: Session, path: str, key: str) -> ConfigUnit | None:
        result = sess.run(
            """
            MATCH (n:ConfigUnit {path: $path, key: $key})
            WHERE NOT EXISTS { MATCH (:ConfigUnit)-[:SUPERSEDES]->(n) }
            RETURN n
            ORDER BY n.created_at DESC
            LIMIT 1
            """,
            path=path,
            key=key,
        )
        record = result.single()
        if record is None:
            return None
        return from_neo4j_properties(dict(record["n"]), self.model_cls)

    def create_version(
        self, sess: Session, new_unit: ConfigUnit, supersedes_id: str, carry_forward_constrains: bool = True
    ) -> ConfigUnit:
        """Same SUPERSEDES + carry-forward-edges pattern as CodeUnitRepository,
        for the CONSTRAINS edge instead of IMPLEMENTS. Diffing stays key-level
        (spec §9.4) — only the ConfigUnit for the changed key gets a new version.
        """
        self.create(sess, new_unit)
        supersedes(sess, new_unit.id, supersedes_id)
        if carry_forward_constrains:
            result = sess.run(
                "MATCH (:ConfigUnit {id: $old_id})-[:CONSTRAINS]->(c:Contract) RETURN c.id AS id",
                old_id=supersedes_id,
            )
            for record in result:
                constrains(sess, new_unit.id, record["id"])
        return new_unit
