from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["formalizer"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(requirement_text: str, resolved_clarifications: list[tuple[str, str]]) -> str:
    parts = [
        (
            "Formalize the following Requirement into a Contract (preconditions, postconditions, "
            "invariants, given/when/then acceptance criteria) plus behavioral Examples that witness "
            "it (spec phase G1). You MUST produce at least 3 examples, and at least 1 must have "
            "edge_case=true (this is a minimum gate, not a coverage guarantee — cover meaningful "
            "behavioral classes, boundary/error paths, not just the count). Each Example is a "
            "concrete input -> expected_output test case, not code."
        ),
        f"\nRequirement:\n{requirement_text}",
    ]
    if resolved_clarifications:
        parts.append(
            "\nResolved clarifications (incorporate these answers):\n"
            + "\n".join(f"- Q: {q}\n  A: {a}" for q, a in resolved_clarifications)
        )
    return "\n".join(parts)
