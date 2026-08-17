from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["critic"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(requirement_text: str, existing_clarifications: list[str] | None = None) -> str:
    parts = [
        (
            "Attack the following Requirement for ambiguity, gaps, contradictions, and boundary "
            "cases (spec phase G0). For each real issue, produce a Clarification question "
            "(mark `blocking=true` only if work cannot proceed without an answer) or an Assumption "
            "(a temporary decision you'd make, with rationale, if the human doesn't answer). Do not "
            "invent problems that aren't there — a clean requirement can have zero clarifications."
        ),
        f"\nRequirement:\n{requirement_text}",
    ]
    if existing_clarifications:
        parts.append(
            "\nAlready-raised clarifications (do not duplicate):\n"
            + "\n".join(f"- {c}" for c in existing_clarifications)
        )
    return "\n".join(parts)
