"""`close-phase <phase-id>` — spec §6 G4 closure checklist, evaluated against
real state instead of a human manually cross-referencing `consistency-check`
and `status` output. Added command, not in spec §13's literal list (same
documented-deviation pattern as `validate`). Never mutates `TodoPhase.status`
itself — that stays a human call.
"""

from __future__ import annotations

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.consistency import run_consistency_checks
from reqgraph.state import io as state_io
from reqgraph.state.paths import phase_todo_path, todo_global_path
from reqgraph.state.schemas import TodoGlobal, TodoPhase


def run(phase_id: str) -> None:
    root = project_root()
    todo_path = phase_todo_path(root, phase_id)
    if not todo_path.exists():
        console.print(f"[red]No phase todo file for {phase_id!r}.[/red]")
        raise typer.Exit(code=1)
    phase_data = TodoPhase.model_validate(state_io.read_json(todo_path))
    task_ids = {t.id for t in phase_data.tasks}

    global_path = todo_global_path(root)
    todo_global = (
        TodoGlobal.model_validate(state_io.read_json(global_path)) if global_path.exists() else None
    )

    with graph_session() as sess:
        violations = run_consistency_checks(sess, root, phase_id=phase_id)

    needs_revalidation_violations = [v for v in violations if v.check_id == "8"]
    other_violations = [v for v in violations if v.check_id != "8"]

    blocking_assumptions = (
        [a for a in todo_global.open_assumptions if task_ids & set(a.blocking_tasks)] if todo_global else []
    )
    blocking_issues = (
        [i for i in todo_global.open_issues if task_ids & set(i.blocking_tasks)] if todo_global else []
    )
    regression_green = bool(todo_global and todo_global.last_regression.result == "green")

    checklist = [
        ("consistency-check green", not other_violations, [f"{v.check_id}: {v.description} ({v.node_id})" for v in other_violations]),
        (
            "no unresolved needs_revalidation for phase scope",
            not needs_revalidation_violations,
            [f"{v.node_id} ({v.detail})" for v in needs_revalidation_violations],
        ),
        (
            "blocking assumptions resolved or explicitly carried",
            not blocking_assumptions,
            [a.text for a in blocking_assumptions],
        ),
        (
            "blocking issues resolved or explicitly carried",
            not blocking_issues,
            [i.issue_id for i in blocking_issues],
        ),
        ("target regression green", regression_green, [] if regression_green else ["no green regression recorded — run `complete` on a task, or rerun the suite"]),
    ]

    console.print(f"[bold]Phase {phase_id} exit criteria:[/bold]")
    all_pass = True
    for criterion, passed, details in checklist:
        mark = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        console.print(f"  {mark}  {criterion}")
        for d in details:
            console.print(f"        - {d}")
        all_pass = all_pass and passed

    if not all_pass:
        console.print(f"[red]Phase {phase_id} is not ready to close.[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Phase {phase_id} meets all exit criteria.[/green]")
