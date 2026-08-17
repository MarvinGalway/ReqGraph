from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["impact_analyst"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(changed_symbol: str, diff_text: str, candidate_contracts: list[str]) -> str:
    return (
        "A technical artifact changed. The candidate Contracts below were selected by "
        "DETERMINISTIC graph traversal (IMPLEMENTS/CONSTRAINS/TESTS/DEPENDS_ON) — you do not get "
        "to shrink this candidate set, only classify risk per contract. For each candidate "
        "Contract, classify risk (none/low/medium/high) with a rationale and a recommended "
        "action. Set open_issue_recommended=true only if you believe this warrants a tracked "
        f"Issue.\n\nChanged symbol: {changed_symbol}\n\nDiff:\n{diff_text}\n\n"
        "Candidate Contracts (id: summary):\n" + "\n".join(f"- {c}" for c in candidate_contracts)
    )
