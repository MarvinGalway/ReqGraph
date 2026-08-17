from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["planner"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(contract_summary: str, requirement_text: str, issue_summary: str | None = None) -> str:
    parts = [
        (
            "Derive one or more authorized Tasks from the following validated Contract (spec phase "
            "G2). A Task represents authorized work, not just 'a function to generate' — give each a "
            "clear Definition of Done and, if you can tell from the contract, the glob patterns of "
            "paths that should be in scope."
        ),
        f"\nContract:\n{contract_summary}",
        f"\nRequirement it formalizes:\n{requirement_text}",
    ]
    if issue_summary:
        parts.append(f"\nThis Task addresses the following authorized Issue:\n{issue_summary}")
    return "\n".join(parts)
