from __future__ import annotations

from reqgraph.graph.models import Assumption
from reqgraph.graph.repositories.base import NodeRepository


class AssumptionRepository(NodeRepository[Assumption]):
    label = "Assumption"
    model_cls = Assumption
