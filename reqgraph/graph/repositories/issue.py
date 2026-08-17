from __future__ import annotations

from reqgraph.graph.models import Issue
from reqgraph.graph.repositories.base import NodeRepository


class IssueRepository(NodeRepository[Issue]):
    label = "Issue"
    model_cls = Issue
