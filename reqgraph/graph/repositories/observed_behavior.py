from __future__ import annotations

from reqgraph.graph.models import ObservedBehavior
from reqgraph.graph.repositories.base import NodeRepository


class ObservedBehaviorRepository(NodeRepository[ObservedBehavior]):
    label = "ObservedBehavior"
    model_cls = ObservedBehavior

    def _embedding_text(self, node: ObservedBehavior) -> str | None:
        return f"given {node.given} when {node.when} observed {node.observed}"
