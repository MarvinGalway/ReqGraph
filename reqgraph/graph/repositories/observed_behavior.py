from __future__ import annotations

from reqgraph.graph.models import ObservedBehavior
from reqgraph.graph.repositories.base import NodeRepository


class ObservedBehaviorRepository(NodeRepository[ObservedBehavior]):
    label = "ObservedBehavior"
    model_cls = ObservedBehavior
