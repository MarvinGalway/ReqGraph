from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import Task
from reqgraph.graph.repositories.base import NodeRepository, from_neo4j_properties


class TaskRepository(NodeRepository[Task]):
    label = "Task"
    model_cls = Task

    def get_by_external_id(self, sess: Session, external_id: str) -> Task | None:
        """Resolves a project-state task id (e.g. "task-01-01") to its Task node.

        `external_id` is the business key used throughout /.project-state/
        task files; `id` (the graph UUID) is what edges reference.
        """
        result = sess.run(
            "MATCH (n:Task {external_id: $external_id}) RETURN n", external_id=external_id
        )
        record = result.single()
        if record is None:
            return None
        return from_neo4j_properties(dict(record["n"]), self.model_cls)
