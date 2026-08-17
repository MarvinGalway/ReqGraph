from __future__ import annotations

from reqgraph.graph.models import Issue
from reqgraph.graph.repositories.base import NodeRepository


class IssueRepository(NodeRepository[Issue]):
    label = "Issue"
    model_cls = Issue

    def _embedding_text(self, node: Issue) -> str | None:
        return f"{node.title} {node.description}".strip() or None
