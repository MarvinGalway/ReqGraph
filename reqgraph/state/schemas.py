"""Pydantic mirrors of todo-templates-v0.2.json, field-for-field.

The `file` key in each JSON template describes *where* the file lives, not
data — that's handled by `state/paths.py` instead, so it's omitted here.
`ProjectFile` is a new minimal addition: spec §11 lists `project.json` in the
file tree but `todo-templates-v0.2.json` never defines its shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from reqgraph import __version__ as REQGRAPH_VERSION


def now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# project.json (new — see plan Ambiguity 1)
# ---------------------------------------------------------------------------


class ProjectFile(BaseModel):
    project: str
    project_mode: Literal["greenfield", "existing-project"] = "greenfield"
    created_at: datetime = Field(default_factory=now)
    reqgraph_version: str = REQGRAPH_VERSION
    # Shell command used by `run-task --verify-red` and `complete`'s regression
    # gate to actually run the target repo's test suite (e.g. "pytest").
    test_command: str | None = None


# ---------------------------------------------------------------------------
# todo-global.json
# ---------------------------------------------------------------------------


class PhaseSummary(BaseModel):
    id: str
    title: str = ""
    status: str = "in_progress"
    tasks_done: int = 0
    tasks_total: int = 0


class OpenAssumption(BaseModel):
    assumption_id: str
    text: str = ""
    blocking_tasks: list[str] = Field(default_factory=list)


class OpenContradiction(BaseModel):
    edge_id: str
    between: list[str] = Field(default_factory=list)
    summary: str = ""


class OpenIssueRef(BaseModel):
    issue_id: str
    classification: str = "unknown"
    blocking_tasks: list[str] = Field(default_factory=list)


class LastRegression(BaseModel):
    at: datetime | None = None
    result: Literal["green", "red", "unknown"] = "unknown"


class BootstrapSummary(BaseModel):
    status: Literal["not_applicable", "scanning", "inferring", "human_review", "complete"] = (
        "not_applicable"
    )
    coverage: float = 0.0


class TodoGlobal(BaseModel):
    project: str
    project_mode: Literal["greenfield", "existing-project"] = "greenfield"
    current_phase: str = ""
    phases: list[PhaseSummary] = Field(default_factory=list)
    open_assumptions: list[OpenAssumption] = Field(default_factory=list)
    open_contradictions: list[OpenContradiction] = Field(default_factory=list)
    open_issues: list[OpenIssueRef] = Field(default_factory=list)
    stale_nodes_count: int = 0
    needs_revalidation_count: int = 0
    last_regression: LastRegression = Field(default_factory=LastRegression)
    bootstrap: BootstrapSummary = Field(default_factory=BootstrapSummary)


# ---------------------------------------------------------------------------
# phases/phase-NN/todo-phase.json
# ---------------------------------------------------------------------------


class PhaseTaskRef(BaseModel):
    id: str
    title: str = ""
    status: Literal["todo", "in_progress", "blocked", "done", "stale"] = "todo"
    depends_on: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None


class TodoPhase(BaseModel):
    phase_id: str
    title: str = ""
    goal: str = ""
    exit_criteria: list[str] = Field(
        default_factory=lambda: [
            "consistency-check green",
            "target regression green",
            "blocking assumptions resolved or explicitly carried",
            "blocking issues resolved or explicitly carried",
            "no unresolved needs_revalidation for phase scope",
        ]
    )
    tasks: list[PhaseTaskRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# phases/phase-NN/tasks/task-NN-NN.json
# ---------------------------------------------------------------------------


class TaskScopeFile(BaseModel):
    target_codeunits: list[str] = Field(default_factory=list)
    target_configunits: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    out_of_scope_policy: str = "report_issue_do_not_modify"


class DefinitionOfDoneFile(BaseModel):
    tests: list[str] = Field(default_factory=list)
    regression: str = "relevant/full suite green as configured"
    fidelity_check: str = "reviewer confirms implementation<->contract<->requirement"
    impact_check: str = "all directly affected contracts evaluated"


class TddLoopState(BaseModel):
    step: Literal[
        "write-tests",
        "verify-red",
        "implement",
        "impact-check",
        "fidelity-check",
        "regression",
        "update-state",
    ] = "write-tests"
    tests_verified_red: bool = False
    notes: str = ""


class ArtifactsGenerated(BaseModel):
    codeunits: list[str] = Field(default_factory=list)
    configunits: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)


class OutOfScopeFinding(BaseModel):
    issue_id: str
    summary: str = ""


class TaskDecision(BaseModel):
    choice: str
    rationale: str = ""
    at: datetime = Field(default_factory=now)


class AssumptionRaised(BaseModel):
    text: str
    graph_node: str | None = None
    status: str = "open"


class TaskFile(BaseModel):
    id: str
    title: str = ""
    status: Literal["todo", "in_progress", "blocked", "done", "stale"] = "todo"
    contract_refs: list[str] = Field(default_factory=list)
    requirement_refs: list[str] = Field(default_factory=list)
    examples_assigned: list[str] = Field(default_factory=list)
    issues_addressed: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    scope: TaskScopeFile = Field(default_factory=TaskScopeFile)
    definition_of_done: DefinitionOfDoneFile = Field(default_factory=DefinitionOfDoneFile)
    tdd_loop_state: TddLoopState = Field(default_factory=TddLoopState)
    artifacts_generated: ArtifactsGenerated = Field(default_factory=ArtifactsGenerated)
    out_of_scope_findings: list[OutOfScopeFinding] = Field(default_factory=list)
    decisions: list[TaskDecision] = Field(default_factory=list)
    assumptions_raised: list[AssumptionRaised] = Field(default_factory=list)
    clarifications_opened: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# issues/issue-<id>.json
# ---------------------------------------------------------------------------


class IssueFile(BaseModel):
    issue_id: str
    workflow_status: Literal[
        "open", "triaging", "ready", "in_progress", "resolved", "closed", "rejected"
    ] = "open"
    classification: str = "unknown"
    reported_by: str = "human"
    found_during_task: str | None = None
    evidence: list[str] = Field(default_factory=list)
    candidate_contracts: list[str] = Field(default_factory=list)
    candidate_codeunits: list[str] = Field(default_factory=list)
    candidate_configunits: list[str] = Field(default_factory=list)
    human_decision: Literal[
        "pending", "investigate", "backlog", "resolve", "reject", "expected_behavior"
    ] = "pending"
    authorized_task: str | None = None


# ---------------------------------------------------------------------------
# bootstrap/bootstrap-state.json
# ---------------------------------------------------------------------------


class BootstrapCounts(BaseModel):
    codeunits: int = 0
    configunits: int = 0
    tests: int = 0
    observed_behaviors: int = 0
    candidate_contracts: int = 0
    candidate_requirements: int = 0
    validated_contracts: int = 0
    validated_requirements: int = 0


class BootstrapState(BaseModel):
    mode: Literal["existing-project"] = "existing-project"
    stage: Literal["scan", "observe", "infer", "human_review", "complete"] = "scan"
    repository_revision: str = ""
    counts: BootstrapCounts = Field(default_factory=BootstrapCounts)
    review_queue: list[str] = Field(default_factory=list)
