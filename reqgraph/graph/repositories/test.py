from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import Test
from reqgraph.graph.repositories.base import NodeRepository, from_neo4j_properties


class TestRepository(NodeRepository[Test]):
    label = "Test"
    model_cls = Test

    def find_by_path_symbol(self, sess: Session, path: str, symbol: str | None) -> Test | None:
        result = sess.run(
            "MATCH (n:Test {path: $path, symbol: $symbol}) RETURN n LIMIT 1",
            path=path,
            symbol=symbol,
        )
        record = result.single()
        if record is None:
            return None
        return from_neo4j_properties(dict(record["n"]), self.model_cls)
