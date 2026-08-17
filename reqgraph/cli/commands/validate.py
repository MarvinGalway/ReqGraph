"""`validate <node-id>` — added command, not in spec §13's literal list.

Spec §6 phase G1 requires human validation of Contract/Example (and,
implicitly, candidate Requirement in the bootstrap path) before
`derive-tasks` can run, but §13 never lists a command for it. This is the
same underlying primitive `bootstrap-review`'s "correct" outcome uses.
"""

from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session

VALIDATABLE_LABELS = {"Contract", "Example", "Requirement"}


def run(
    node_id: str,
    approve: Annotated[bool, typer.Option("--approve/--reject", help="Approve or reject")] = True,
    by: Annotated[str, typer.Option(help="human:<id> performing the validation")] = "human",
) -> None:
    with graph_session() as sess:
        record = sess.run("MATCH (n {id: $id}) RETURN labels(n)[0] AS label", id=node_id).single()
        if record is None:
            raise typer.BadParameter(f"no node with id={node_id!r}")
        label = record["label"]
        if label not in VALIDATABLE_LABELS:
            raise typer.BadParameter(f"{label} is not validatable (must be one of {VALIDATABLE_LABELS})")

        new_status = "validated" if approve else "disputed"
        sess.run(
            f"MATCH (n:{label} {{id: $id}}) SET n.knowledge_status = $status, "
            "n.trust = CASE WHEN $status = 'validated' THEN 'human-validated' ELSE n.trust END, "
            "n.updated_at = datetime()",
            id=node_id,
            status=new_status,
        )
        if label == "Contract" and approve:
            sess.run(
                "MATCH (c:Contract {id: $id})-[f:FORMALIZES]->(:Requirement) SET f.reviewed_by = $by",
                id=node_id,
                by=by,
            )

    verb = "Validated" if approve else "Rejected (disputed)"
    console.print(f"[green]{verb}[/green] {label} {node_id} (by={by})")
