from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["reverse_analyst"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(observed_behaviors: list[str]) -> str:
    return (
        "The following ObservedBehavior records were extracted from an existing codebase's "
        "tests/code/config (spec phase B2/B3, legacy bootstrap). Group the coherent ones and "
        "propose ONE candidate Requirement, Contract, and set of behavioral Examples that would "
        "explain them. Everything you produce is `knowledge_status=inferred` — you are proposing "
        "a hypothesis for human review, not asserting ground truth. The code is never assumed to "
        "be the original intent.\n\nObserved behaviors:\n"
        + "\n".join(f"- {b}" for b in observed_behaviors)
    )
