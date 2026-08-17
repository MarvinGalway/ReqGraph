"""Per-role structured-output models. Passed directly as `output_format=` to
`client.messages.parse()` (anthropic>=0.68 generates the JSON schema from the
pydantic model and returns a validated instance via `.parsed_output`).

Note: `librarian` has no dedicated schema here — no CLI command in this pass
invokes it as a single-shot structured call; it's reserved for future
graph-extraction/embedding/compression support work.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# critic — run-critic
# ---------------------------------------------------------------------------


class ClarificationDraft(BaseModel):
    question: str
    blocking: bool = True


class AssumptionDraft(BaseModel):
    text: str
    rationale: str


class ContradictionDraft(BaseModel):
    other_requirement_id: str
    summary: str


class CriticOutput(BaseModel):
    clarifications: list[ClarificationDraft] = Field(default_factory=list)
    assumptions: list[AssumptionDraft] = Field(default_factory=list)
    contradictions: list[ContradictionDraft] = Field(default_factory=list)
    summary: str


# ---------------------------------------------------------------------------
# formalizer — formalize (also reused by reverse_analyst)
# ---------------------------------------------------------------------------


class AcceptanceCriterionDraft(BaseModel):
    given: str
    when: str
    then: str


class ContractDraft(BaseModel):
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCriterionDraft] = Field(default_factory=list)


class BehavioralSignatureDraft(BaseModel):
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ExampleDraft(BaseModel):
    input: dict = Field(default_factory=dict)
    expected_output: dict = Field(default_factory=dict)
    edge_case: bool = False
    behavioral_signature: BehavioralSignatureDraft = Field(default_factory=BehavioralSignatureDraft)


class FormalizerOutput(BaseModel):
    contract: ContractDraft
    examples: list[ExampleDraft]


# ---------------------------------------------------------------------------
# planner — derive-tasks
# ---------------------------------------------------------------------------


class TaskDraft(BaseModel):
    title: str
    definition_of_done: str
    allowed_paths: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    tasks: list[TaskDraft]


# ---------------------------------------------------------------------------
# reverse_analyst — bootstrap-infer
# ---------------------------------------------------------------------------


class CandidateRequirementDraft(BaseModel):
    text: str


class ReverseAnalystOutput(BaseModel):
    requirement: CandidateRequirementDraft
    contract: ContractDraft
    examples: list[ExampleDraft]
    rationale: str


# ---------------------------------------------------------------------------
# impact_analyst — impact
# ---------------------------------------------------------------------------

RiskLevel = Literal["none", "low", "medium", "high"]


class ContractImpactDraft(BaseModel):
    contract_id: str
    risk: RiskLevel
    rationale: str
    recommended_action: str


class ImpactAnalystOutput(BaseModel):
    contract_impacts: list[ContractImpactDraft] = Field(default_factory=list)
    overall_risk: RiskLevel
    open_issue_recommended: bool = False
    issue_summary: str | None = None


# ---------------------------------------------------------------------------
# issue_triage — triage-issue
# ---------------------------------------------------------------------------

IssueClassification = Literal[
    "unknown",
    "suspected_bug",
    "confirmed_bug",
    "expected_behavior",
    "specification_gap",
    "requirement_ambiguity",
    "regression",
    "tech_debt",
    "duplicate",
]


class IssueTriageOutput(BaseModel):
    classification: IssueClassification
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    rationale: str
    candidate_contract_ids: list[str] = Field(default_factory=list)
    candidate_codeunit_ids: list[str] = Field(default_factory=list)
    candidate_configunit_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# reviewer — complete's fidelity gate
# ---------------------------------------------------------------------------


class ReviewerOutput(BaseModel):
    verdict: Literal["pass", "fail"]
    contract_fidelity_notes: str
    requirement_fidelity_notes: str
    concerns: list[str] = Field(default_factory=list)
