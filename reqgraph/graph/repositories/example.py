from __future__ import annotations

from reqgraph.graph.models import Example
from reqgraph.graph.repositories.base import NodeRepository


class ExampleRepository(NodeRepository[Example]):
    label = "Example"
    model_cls = Example
