"""Pydantic node/edge models mirroring graph-schema-v0.2.json 1:1.

Every node label defined in `graph-schema-v0.2.json`'s `nodes` block has a
matching model here with the same field names. `BaseNode` carries the fields
listed under `common_node_fields`. Edge payloads (fields carried by an edge,
not a node) are modeled separately in `EdgeFields` subclasses used by
`graph/repositories/edges.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

KnowledgeStatus = Literal[
    "observed", "inferred", "generated", "validated", "disputed", "stale"
]
VerificationStatus = Literal[
    "not_applicable", "unknown", "needs_revalidation", "verified", "failed"
]


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class BaseNode(BaseModel):
    """Fields common to every node label (graph-schema-v0.2.json: common_node_fields)."""

    # Neo4j node properties are flat (no nested maps). Fields listed here are
    # JSON-encoded to a string on write and decoded back on read by
    # graph/repositories/base.py. Subclasses override with their own nested
    # fields (see Contract.acceptance, Example.behavioral_signature, etc).
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset()

    id: str = Field(default_factory=new_id)
    knowledge_status: KnowledgeStatus = "observed"
    verification_status: VerificationStatus = "not_applicable"
    created_by: str = "human"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    source_refs: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None


# ---------------------------------------------------------------------------
# Intent & Semantics
# ---------------------------------------------------------------------------


class Requirement(BaseNode):
    text: str
    source: Literal["person", "document", "ticket", "reverse-engineered"] = "person"
    trust: Literal[
        "external-unverified", "external-verified", "human-validated"
    ] = "external-unverified"
    origin_mode: Literal["greenfield", "legacy-bootstrap"] = "greenfield"


class Clarification(BaseNode):
    question: str
    answer: str | None = None
    answered_by: str | None = None
    blocking: bool = True


class Assumption(BaseNode):
    text: str
    rationale: str
    decision_status: Literal["open", "validated", "rejected"] = "open"


# ---------------------------------------------------------------------------
# Behavioral Specification
# ---------------------------------------------------------------------------


class AcceptanceCriterion(BaseModel):
    given: str
    when: str
    then: str


class Contract(BaseNode):
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset({"acceptance"})

    summary: str = ""
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    origin_mode: Literal["greenfield", "legacy-bootstrap"] = "greenfield"


class BehavioralSignature(BaseModel):
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Example(BaseNode):
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"input", "expected_output", "behavioral_signature"}
    )

    summary: str = ""
    input: dict | list | str | int | float | bool | None = None
    expected_output: dict | list | str | int | float | bool | None = None
    edge_case: bool = False
    behavioral_signature: BehavioralSignature = Field(default_factory=BehavioralSignature)
    origin: Literal["formalizer", "inferred-from-existing-test", "human"] = "formalizer"


# ---------------------------------------------------------------------------
# Planning & Orchestration
# ---------------------------------------------------------------------------


class TaskScope(BaseModel):
    target_contracts: list[str] = Field(default_factory=list)
    target_codeunits: list[str] = Field(default_factory=list)
    target_configunits: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    choice: str
    rationale: str
    at: datetime = Field(default_factory=now)


class Task(BaseNode):
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset({"scope", "decisions"})

    title: str
    phase: str = ""
    workflow_status: Literal["todo", "in_progress", "blocked", "done", "stale"] = "todo"
    definition_of_done: str = ""
    scope: TaskScope = Field(default_factory=TaskScope)
    decisions: list[Decision] = Field(default_factory=list)
    # Business key used by project-state files (e.g. "task-01-01"), distinct
    # from `id` (graph UUID). See implementation plan §"context <task-id>".
    external_id: str | None = None


# ---------------------------------------------------------------------------
# Implementation & Verification
# ---------------------------------------------------------------------------


class CodeUnit(BaseNode):
    path: str
    symbol: str
    kind: Literal["function", "class", "method", "module", "other"] = "function"
    hash: str = ""
    git_commit: str | None = None
    language: str | None = None


class ConfigUnit(BaseNode):
    path: str
    key: str
    kind: Literal[
        "setting", "feature_flag", "environment", "route_config", "framework_config", "other"
    ] = "setting"
    value_hash: str = ""
    scope_hint: Literal["local", "subsystem", "project-wide", "unknown"] = "unknown"


class Test(BaseNode):
    path: str
    symbol: str | None = None
    framework: str | None = None
    last_result: Literal["red", "green", "skipped", "error", "not-run"] = "not-run"


# ---------------------------------------------------------------------------
# Quality & Investigation
# ---------------------------------------------------------------------------


class Issue(BaseNode):
    title: str
    description: str = ""
    reported_by: str = "human"
    workflow_status: Literal[
        "open", "triaging", "ready", "in_progress", "resolved", "closed", "rejected"
    ] = "open"
    classification: Literal[
        "unknown",
        "suspected_bug",
        "confirmed_bug",
        "expected_behavior",
        "specification_gap",
        "requirement_ambiguity",
        "regression",
        "tech_debt",
        "duplicate",
    ] = "unknown"
    severity: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    resolution: str | None = None


# ---------------------------------------------------------------------------
# Observed Evidence
# ---------------------------------------------------------------------------


class ObservedBehavior(BaseNode):
    given: str
    when: str
    observed: str
    evidence_type: Literal["test", "static-code", "runtime", "config", "documentation"] = (
        "static-code"
    )
    confidence: Literal["low", "medium", "high"] = "medium"


NODE_LABELS: dict[str, type[BaseNode]] = {
    "Requirement": Requirement,
    "Clarification": Clarification,
    "Assumption": Assumption,
    "Contract": Contract,
    "Example": Example,
    "Task": Task,
    "CodeUnit": CodeUnit,
    "ConfigUnit": ConfigUnit,
    "Test": Test,
    "Issue": Issue,
    "ObservedBehavior": ObservedBehavior,
}

EDGE_TYPES: tuple[str, ...] = (
    "CLARIFIES",
    "FORMALIZES",
    "WITNESSES",
    "DERIVES_FROM",
    "GENERATED_BY",
    "GENERATED_FROM",
    "IMPLEMENTS",
    "CONSTRAINS",
    "TESTS",
    "DEPENDS_ON",
    "CONTRADICTS",
    "REFINES",
    "SUPERSEDES",
    "EVIDENCES",
    "SUPPORTS",
    "INFERRED_FROM",
    "FOUND_DURING",
    "AFFECTS",
    "VIOLATES",
    "EXPLAINED_BY",
    "BLOCKS",
    "ADDRESSES",
)
