"""Applies models-config-v0.2.json's `retrieval.context_budget_quotas` to a
pool of candidate context items, dropping lowest-priority items first within
an overflowing category. Token counts are a crude chars/4 estimate — good
enough for budget allocation, not meant to match a real tokenizer exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

CATEGORY_QUOTAS: dict[str, float] = {
    "contracts_and_requirements": 0.28,
    "validated_examples": 0.22,
    "constraints_assumptions_issues": 0.18,
    "implementation_and_dependency_interfaces": 0.17,
    "state_todo_decisions": 0.10,
    "observed_evidence": 0.05,
}

# Lower number = higher priority = kept first when a category overflows.
PRIORITY_BY_KNOWLEDGE_STATUS: dict[str, int] = {
    "validated": 0,
    "generated": 1,
    "observed": 1,
    "inferred": 2,
    "disputed": 3,
    "stale": 4,
}


@dataclass
class BudgetItem:
    category: str
    text: str
    priority: int = 2
    tokens: int = 0

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = estimate_tokens(self.text)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def allocate(items: list[BudgetItem], total_budget: int) -> list[BudgetItem]:
    selected: list[BudgetItem] = []
    for category, share in CATEGORY_QUOTAS.items():
        category_budget = int(total_budget * share)
        category_items = sorted(
            (i for i in items if i.category == category), key=lambda i: i.priority
        )
        used = 0
        for item in category_items:
            if used + item.tokens > category_budget:
                continue
            selected.append(item)
            used += item.tokens
    return selected
