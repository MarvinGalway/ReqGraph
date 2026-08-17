"""Role config mirroring models-config-v0.2.json's `roles` block.

`codegen` is intentionally omitted — per the confirmed architecture, Codegen
is an external agent (Claude Code, OpenCode, a human), not an LLM role
graph-cli invokes itself; graph-cli only gates/records around it (see G3
implementation plan). `reviewer` IS represented despite that, because it's
graph-cli's own automated fidelity check on `complete`, structurally
separate from whatever agent wrote the code — the spec's "must differ from
codegen" rule is satisfied by construction, not by model selection.

**Deviation from the literal JSON (documented, not silent):** the JSON's
per-role `temperature` values are incompatible with current-generation
Claude models, which reject non-default `temperature` and use
`thinking`/`output_config.effort` instead. Roles on those models set
`effort` and leave `temperature=None`; `librarian` stays on an
older-generation model that still accepts `temperature` literally.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class RoleConfig:
    name: str
    pipeline: str
    purpose: str
    profile: str
    default_model: str
    effort: Effort | None = None
    temperature: float | None = None
    hard_rule: str | None = None


ROLES: dict[str, RoleConfig] = {
    "critic": RoleConfig(
        name="critic",
        pipeline="greenfield",
        purpose="attack requirements: ambiguity, gaps, contradictions, edge cases",
        profile="strong reasoning, broad context",
        default_model="claude-opus-5",
        effort="high",
    ),
    "formalizer": RoleConfig(
        name="formalizer",
        pipeline="greenfield + legacy",
        purpose="contracts and behavioral examples; candidate specs in legacy mode",
        profile="strong reasoning",
        default_model="claude-opus-5",
        effort="high",
    ),
    "planner": RoleConfig(
        name="planner",
        pipeline="shared",
        purpose="derive authorized tasks from validated contracts/issues",
        profile="reasoning",
        default_model="claude-sonnet-5",
        effort="medium",
    ),
    "reverse_analyst": RoleConfig(
        name="reverse_analyst",
        pipeline="existing-project bootstrap",
        purpose="infer ObservedBehavior and candidate behavioral/semantic knowledge from repository evidence",
        profile="strong reasoning + code understanding",
        default_model="claude-opus-5",
        effort="high",
        hard_rule="never mark inferred intent as validated",
    ),
    "impact_analyst": RoleConfig(
        name="impact_analyst",
        pipeline="maintenance",
        purpose="evaluate semantic impact of changed CodeUnit/ConfigUnit on candidate contracts",
        profile="strong reasoning + diff/code understanding",
        default_model="claude-opus-5",
        effort="high",
        hard_rule=(
            "candidate selection starts from deterministic graph/static analysis; "
            "analyst does not silently shrink the safety set"
        ),
    ),
    "issue_triage": RoleConfig(
        name="issue_triage",
        pipeline="shared",
        purpose="assist Issue classification, evidence gathering and candidate links",
        profile="reasoning",
        default_model="claude-sonnet-5",
        effort="medium",
        hard_rule="classification does not authorize code modification",
    ),
    "librarian": RoleConfig(
        name="librarian",
        pipeline="shared",
        purpose="graph extraction/update, embeddings, todo compression, provenance",
        profile="small/economic, high volume",
        default_model="claude-haiku-4-5-20251001",
        temperature=0.0,
    ),
    "reviewer": RoleConfig(
        name="reviewer",
        pipeline="shared",
        purpose="implementation<->contract<->requirement fidelity and regression review",
        profile="medium-high reasoning",
        default_model="claude-opus-5",
        effort="medium",
        hard_rule="reports fidelity issues; does not authorize further modification",
    ),
}


def resolve_model(role: RoleConfig) -> str:
    env_var = f"REQGRAPH_MODEL_{role.name.upper()}"
    return os.environ.get(env_var, role.default_model)
