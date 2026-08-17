from __future__ import annotations

from reqgraph.llm.prompts._shared import build_system_prompt
from reqgraph.llm.roles import ROLES

ROLE = ROLES["issue_triage"]


def system_prompt() -> str:
    return build_system_prompt(ROLE.name, ROLE.purpose, ROLE.profile, ROLE.hard_rule)


def user_prompt(issue_title: str, issue_description: str, graph_neighborhood: str) -> str:
    return (
        "Triage the following Issue: classify it, estimate severity, and suggest candidate "
        "linked Contract/CodeUnit/ConfigUnit ids from the graph neighborhood below. Your "
        "classification does NOT authorize any code modification — it only informs the human "
        "decision in `authorize-issue`.\n\n"
        f"Title: {issue_title}\nDescription: {issue_description}\n\n"
        f"Graph neighborhood:\n{graph_neighborhood}"
    )
