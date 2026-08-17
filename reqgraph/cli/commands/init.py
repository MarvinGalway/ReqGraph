from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.schema import apply_schema
from reqgraph.state import io as state_io
from reqgraph.state.paths import (
    bootstrap_state_path,
    decisions_log_path,
    project_json_path,
    todo_global_path,
)
from reqgraph.state.schemas import BootstrapState, ProjectFile, TodoGlobal


def run(
    project: Annotated[str, typer.Option(help="Project name")],
    mode: Annotated[str, typer.Option(help="greenfield | existing-project")] = "greenfield",
    with_vector: Annotated[
        bool, typer.Option("--with-vector", help="Also create vector indexes (embeddings deferred otherwise)")
    ] = False,
    test_command: Annotated[
        str | None,
        typer.Option(help="Shell command to run the target repo's test suite, e.g. 'pytest'"),
    ] = None,
) -> None:
    if mode not in ("greenfield", "existing-project"):
        raise typer.BadParameter("mode must be 'greenfield' or 'existing-project'")

    root = project_root()
    with graph_session() as sess:
        applied = apply_schema(sess, with_vector=with_vector)

    project_file = ProjectFile(project=project, project_mode=mode, test_command=test_command)
    state_io.write_json(project_json_path(root), project_file.model_dump(mode="json"))

    todo_global = TodoGlobal(project=project, project_mode=mode)
    state_io.write_json(todo_global_path(root), todo_global.model_dump(mode="json"))

    if mode == "existing-project":
        bootstrap_state = BootstrapState()
        state_io.write_json(bootstrap_state_path(root), bootstrap_state.model_dump(mode="json"))

    decisions_log = decisions_log_path(root)
    if not decisions_log.exists():
        state_io.append_text(decisions_log, f"# Decisions log — {project}\n\n")

    console.print(f"[green]Initialized ReqGraph project[/green] '{project}' (mode={mode}).")
    console.print(f"Applied {len(applied)} schema statements to Neo4j.")
    console.print(f"Project state at {root / '.project-state'}")
    if test_command:
        console.print(f"test_command = {test_command!r}")
    else:
        console.print(
            "[yellow]No --test-command set — `run-task --verify-red` and `complete` will "
            "require --test-command explicitly until you set one.[/yellow]"
        )
