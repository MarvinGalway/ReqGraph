from __future__ import annotations

from rich.table import Table

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.state import io as state_io
from reqgraph.state.paths import todo_global_path


def run() -> None:
    root = project_root()
    todo_path = todo_global_path(root)
    if not todo_path.exists():
        console.print("[red]No ReqGraph project here — run `graph-cli init` first.[/red]")
        raise SystemExit(1)
    todo_global = state_io.read_json(todo_path)

    with graph_session() as sess:
        result = sess.run(
            """
            MATCH (n)
            WHERE any(l IN labels(n) WHERE l IN
                ['Requirement','Clarification','Assumption','Contract','Example','Task',
                 'CodeUnit','ConfigUnit','Test','Issue','ObservedBehavior'])
            RETURN labels(n)[0] AS label, n.knowledge_status AS knowledge_status, count(*) AS n
            """
        )
        counts: dict[str, dict[str, int]] = {}
        for record in result:
            counts.setdefault(record["label"], {})[record["knowledge_status"]] = record["n"]

        open_issues = sess.run(
            "MATCH (i:Issue) WHERE NOT i.workflow_status IN ['closed','resolved','rejected'] RETURN count(i) AS n"
        ).single()["n"]
        open_contradictions = sess.run(
            "MATCH ()-[r:CONTRADICTS {status:'open'}]->() RETURN count(r) AS n"
        ).single()["n"]
        needs_revalidation = sess.run(
            "MATCH (n) WHERE n.verification_status = 'needs_revalidation' RETURN count(n) AS n"
        ).single()["n"]

    console.print(f"[bold]Project:[/bold] {todo_global.get('project')} ({todo_global.get('project_mode')})")
    console.print(f"[bold]Current phase:[/bold] {todo_global.get('current_phase') or '(none)'}")

    table = Table(title="Node counts by knowledge_status")
    table.add_column("Label")
    table.add_column("Status")
    table.add_column("Count", justify="right")
    for label, statuses in sorted(counts.items()):
        for status_name, n in sorted(statuses.items()):
            table.add_row(label, status_name, str(n))
    console.print(table)

    console.print(f"Open Issues: {open_issues}")
    console.print(f"Open CONTRADICTS: {open_contradictions}")
    console.print(f"needs_revalidation: {needs_revalidation}")
    console.print(f"stale_nodes_count (last recorded): {todo_global.get('stale_nodes_count', 0)}")
