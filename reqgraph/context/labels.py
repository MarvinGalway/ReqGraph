"""[OBSERVED]/[INFERRED]/... status labeling, per models-config-v0.2.json's
`retrieval.status_labels_in_context`.
"""

from __future__ import annotations

_KNOWLEDGE_LABELS = {
    "observed": "OBSERVED",
    "inferred": "INFERRED",
    "generated": "GENERATED",
    "validated": "VALIDATED",
    "disputed": "DISPUTED",
    "stale": "STALE",
}

_VERIFICATION_LABELS = {
    "needs_revalidation": "NEEDS_REVALIDATION",
    "failed": "FAILED",
}


def status_label(knowledge_status: str, verification_status: str | None = None) -> str:
    """A node's primary label is its knowledge_status; verification_status
    (needs_revalidation/failed) is appended when it adds information beyond
    the knowledge_status alone.
    """
    label = _KNOWLEDGE_LABELS.get(knowledge_status, knowledge_status.upper())
    extra = _VERIFICATION_LABELS.get(verification_status or "")
    return f"[{label}][{extra}]" if extra else f"[{label}]"
