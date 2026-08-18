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
from reqgraph.llm.embeddings import get_embedding_provider

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


def _to_native(value: Any) -> Any:
    """The driver returns its own `neo4j.time.DateTime`/`Date`/`Time`/
    `Duration` wrapper types for temporal properties (`created_at`,
    `updated_at`, ...) — not stdlib `datetime`/`date`/`time`/`timedelta`.
    Pydantic's `datetime` validator doesn't accept them (no test ever caught
    this: every integration test wipes the graph before running, so nothing
    ever read back a node that already existed — the only path that
    round-trips a real stored value through here). `.to_native()` is the
    driver's own conversion, present on every temporal wrapper type.
    """
    to_native = getattr(value, "to_native", None)
    return to_native() if callable(to_native) else value


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
        data[key] = _to_native(value)
    return model_cls.model_validate(data)


class NodeRepository(Generic[T]):
    """CRUD for a single node label. Subclasses set `label` and `model_cls`."""

    label: str
    model_cls: type[T]

    def _embedding_text(self, node: T) -> str | None:
        """Overridden by the 5 vector-eligible repos (Requirement, Contract,
        Example, ObservedBehavior, Issue) to return the text that should be
        embedded. Returning None (the default) means this label never gets
        an embedding — correct for every other repo.
        """
        return None

    def create(self, sess: Session, node: T) -> T:
        if node.embedding is None:
            text = self._embedding_text(node)
            provider = get_embedding_provider() if text else None
            if provider is not None and text is not None:
                node.embedding = provider.embed(text)
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

