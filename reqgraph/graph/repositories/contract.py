from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import Contract
from reqgraph.graph.repositories.base import NodeRepository


class ContractRepository(NodeRepository[Contract]):
    label = "Contract"
    model_cls = Contract

    def behavioral_coverage(self, sess: Session, contract_id: str) -> tuple[int, int]:
        """Returns (validated_example_count, validated_edge_case_count) for a Contract.

        Used by `formalize`'s gate and consistency-check #2 (spec §6 G1: >=3
        Examples, >=1 edge case, minimum gate not a coverage guarantee).
        """
        result = sess.run(
            """
            MATCH (e:Example {knowledge_status: 'validated'})-[:WITNESSES]->(c:Contract {id: $id})
            RETURN count(e) AS total, sum(CASE WHEN e.edge_case THEN 1 ELSE 0 END) AS edge_cases
            """,
            id=contract_id,
        )
        record = result.single()
        if record is None:
            return (0, 0)
        return (record["total"] or 0, record["edge_cases"] or 0)
