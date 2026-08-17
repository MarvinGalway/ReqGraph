from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session


def run(
    node_id: str,
    status: Annotated[str, typer.Option(help="verified | failed")],
) -> None:
    if status not in ("verified", "failed"):
        raise typer.BadParameter("status must be 'verified' or 'failed'")

    with graph_session() as sess:
        result = sess.run(
            "MATCH (n {id: $id}) SET n.verification_status = $status, n.updated_at = datetime() "
            "RETURN labels(n)[0] AS label",
            id=node_id,
            status=status,
        )
        record = result.single()
        if record is None:
            raise typer.BadParameter(f"no node with id={node_id!r}")

    console.print(f"{record['label']} {node_id}: verification_status={status}")
    if status == "failed":
        console.print(f"  Consider `graph-cli open-issue --title '...' --affects {node_id}`.")
