"""Generic CRUD helpers shared by every per-label repository.

Neo4j node properties are flat: no nested maps/objects as values (arrays of
primitives are fine). Fields listed in a model's `JSON_FIELDS` are
JSON-encoded to a string on write and decoded back on read, so pydantic
models with nested structures (Contract.acceptance, Example.input, etc.)
round-trip losslessly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from neo4j import Session
from pydantic import BaseModel

from reqgraph.graph.models import BaseNode

T = TypeVar("T", bound=BaseNode)


def to_neo4j_properties(model: BaseNode) -> dict[str, Any]:
    data = model.model_dump(mode="json")
    json_fields = model.JSON_FIELDS
    props: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if key in json_fields:
            props[key] = json.dumps(value)
        else:
            props[key] = value
    return props


def from_neo4j_properties(props: dict[str, Any], model_cls: type[T]) -> T:
    json_fields = model_cls.JSON_FIELDS
    data: dict[str, Any] = {}
    for key, value in dict(props).items():
        if key in json_fields and isinstance(value, str):
            try:
                data[key] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        data[key] = value
    return model_cls.model_validate(data)


class NodeRepository(Generic[T]):
    """CRUD for a single node label. Subclasses set `label` and `model_cls`."""

    label: str
    model_cls: type[T]

    def create(self, sess: Session, node: T) -> T:
        props = to_neo4j_properties(node)
        sess.run(f"CREATE (n:{self.label} $props)", props=props)
        return node

    def get(self, sess: Session, node_id: str) -> T | None:
        result = sess.run(f"MATCH (n:{self.label} {{id: $id}}) RETURN n", id=node_id)
        record = result.single()
        if record is None:
            return None
        return from_neo4j_properties(dict(record["n"]), self.model_cls)

    def list_all(self, sess: Session, **filters: Any) -> list[T]:
        where = " AND ".join(f"n.{k} = ${k}" for k in filters) if filters else "true"
        result = sess.run(f"MATCH (n:{self.label}) WHERE {where} RETURN n", **filters)
        return [from_neo4j_properties(dict(r["n"]), self.model_cls) for r in result]

    def update_fields(self, sess: Session, node_id: str, **fields: Any) -> None:
        fields = {**fields, "updated_at": datetime.now(UTC).isoformat()}
        set_clause = ", ".join(f"n.{k} = $props.{k}" for k in fields)
        sess.run(
            f"MATCH (n:{self.label} {{id: $id}}) SET {set_clause}",
            id=node_id,
            props=fields,
        )

    def delete(self, sess: Session, node_id: str) -> None:
        sess.run(f"MATCH (n:{self.label} {{id: $id}}) DETACH DELETE n", id=node_id)


class EdgePayload(BaseModel):
    """Base for edge-field payloads (graph-schema-v0.2.json edges[*].fields)."""

