from __future__ import annotations

from reqgraph.graph.models import Clarification
from reqgraph.graph.repositories.base import NodeRepository


class ClarificationRepository(NodeRepository[Clarification]):
    label = "Clarification"
    model_cls = Clarification
