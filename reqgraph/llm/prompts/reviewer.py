from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["reviewer"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(
    contract_text: str,
    requirement_text: str,
    codeunit_sources: list[str],
    test_sources: list[str],
) -> str:
    parts = [
        (
            "Review whether the implementation below is faithful to the Contract it claims to "
            "implement, and whether that Contract in turn is faithful to the Requirement. You are "
            "a different check from whoever wrote this code — your job is to catch fidelity gaps, "
            "not to rewrite anything. Set verdict='fail' if the code doesn't actually satisfy the "
            "Contract's preconditions/postconditions/invariants/acceptance criteria, or if the "
            "Contract itself misrepresents the Requirement. List concrete concerns, not vague "
            "impressions."
        ),
        f"\nRequirement:\n{requirement_text}",
        f"\nContract:\n{contract_text}",
    ]
    if codeunit_sources:
        parts.append("\nImplementation (CodeUnit source):\n" + "\n\n".join(codeunit_sources))
    if test_sources:
        parts.append("\nTests (Test source):\n" + "\n\n".join(test_sources))
    return "\n".join(parts)
