from __future__ import annotations

from neo4j import Session

from reqgraph.graph.models import Requirement
from reqgraph.graph.repositories.base import NodeRepository
from reqgraph.graph.repositories.edges import supersedes


class RequirementRepository(NodeRepository[Requirement]):
    label = "Requirement"
    model_cls = Requirement

    def _embedding_text(self, node: Requirement) -> str | None:
        return node.text

    def create_version(
        self, sess: Session, new_requirement: Requirement, supersedes_id: str
    ) -> Requirement:
        """Writes a new Requirement version and links it -[:SUPERSEDES]-> the prior one.

        Per spec §4.3, the prior node is left untouched (historical); callers
        typically follow up with `graph-cli invalidate <old-id>` to cascade
        `knowledge_status='stale'` down the derived branch.
        """
        self.create(sess, new_requirement)
        supersedes(sess, new_requirement.id, supersedes_id)
        return new_requirement
