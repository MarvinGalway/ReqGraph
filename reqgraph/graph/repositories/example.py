from __future__ import annotations

from reqgraph.graph.models import Example
from reqgraph.graph.repositories.base import NodeRepository


class ExampleRepository(NodeRepository[Example]):
    label = "Example"
    model_cls = Example

    def _embedding_text(self, node: Example) -> str | None:
        parts = [str(node.input), str(node.expected_output), *node.behavioral_signature.tags]
        return " ".join(parts) or None
