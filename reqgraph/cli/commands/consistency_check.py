from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.consistency import run_consistency_checks


def run(
    phase: Annotated[str | None, typer.Option(help="Phase id for check #8 (unresolved needs_revalidation at close)")] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Exit nonzero if any violation is found")] = False,
) -> None:
    root = project_root()
    with graph_session() as sess:
        violations = run_consistency_checks(sess, root, phase_id=phase)

    if not violations:
        console.print("[green]consistency-check: no violations found.[/green]")
        return

    table = Table(title=f"consistency-check: {len(violations)} violation(s)")
    table.add_column("Check")
    table.add_column("Description")
    table.add_column("Node")
    table.add_column("Detail")
    for v in violations:
        table.add_row(v.check_id, v.description, v.node_id, v.detail)
    console.print(table)

    if strict:
        raise typer.Exit(code=1)
