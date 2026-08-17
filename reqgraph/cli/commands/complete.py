from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.repositories.registry import tasks
from reqgraph.state import io as state_io
from reqgraph.state.paths import decisions_log_path, phase_todo_path, task_file_path
from reqgraph.state.schemas import TaskFile, TodoPhase


def run(
    task_id: str,
    regression: Annotated[str, typer.Option(help="green | red | unknown — result of the relevant/full test suite")] = "unknown",
    fidelity_confirmed: Annotated[
        bool, typer.Option("--fidelity-confirmed", help="Reviewer confirmed implementation<->contract<->requirement")
    ] = False,
) -> None:
    with graph_session() as sess:
        task = tasks.get_by_external_id(sess, task_id)
        if task is None:
            raise typer.BadParameter(f"no Task with external_id={task_id!r}")
        phase = task.phase or "phase-01"

        root = project_root()
        task_file_p = task_file_path(root, phase, task_id)
        if not task_file_p.exists():
            raise typer.BadParameter(f"no task file at {task_file_p}")
        data = TaskFile.model_validate(state_io.read_json(task_file_p))

        failures = []
        artifacts = data.artifacts_generated
        if not (artifacts.codeunits or artifacts.configunits or artifacts.tests):
            failures.append("no artifacts recorded (run `run-task --record-...` first)")
        if regression != "green":
            failures.append(f"regression={regression}, expected green")
        if not fidelity_confirmed:
            failures.append("fidelity check not confirmed (--fidelity-confirmed)")

        if failures:
            console.print(f"[red]Cannot complete {task_id}, Definition of Done not met:[/red]")
            for f in failures:
                console.print(f"  - {f}")
            raise typer.Exit(code=1)

        tasks.update_fields(sess, task.id, workflow_status="done")

    data.status = "done"
    state_io.write_json(task_file_p, data.model_dump(mode="json"))

    todo_path = phase_todo_path(root, phase)
    if todo_path.exists():
        phase_data = TodoPhase.model_validate(state_io.read_json(todo_path))
        for t in phase_data.tasks:
            if t.id == task_id:
                t.status = "done"
        state_io.write_json(todo_path, phase_data.model_dump(mode="json"))

    state_io.append_text(decisions_log_path(root), f"- Task {task_id} completed (regression={regression}).\n")
    console.print(f"[green]Task {task_id} -> done[/green]")
