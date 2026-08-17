from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.models import Issue
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import codeunits, configunits, issues, tasks
from reqgraph.state import io as state_io
from reqgraph.state.paths import issue_file_path
from reqgraph.state.schemas import IssueFile


def run(
    title: Annotated[str, typer.Option(help="Issue title")],
    description: Annotated[str, typer.Option(help="Issue description")] = "",
    reported_by: Annotated[str, typer.Option(help="human:<id> | llm:<model> | test | bootstrap")] = "human",
    blocks: Annotated[str | None, typer.Option(help="Task external_id this Issue blocks")] = None,
    found_during: Annotated[str | None, typer.Option(help="Task external_id this was found during")] = None,
    affects: Annotated[str | None, typer.Option(help="CodeUnit or ConfigUnit id this Issue affects")] = None,
) -> None:
    root = project_root()
    issue = Issue(title=title, description=description, reported_by=reported_by)

    with graph_session() as sess:
        issues.create(sess, issue)

        if affects:
            if codeunits.get(sess, affects) is None and configunits.get(sess, affects) is None:
                raise typer.BadParameter(f"no CodeUnit or ConfigUnit with id={affects!r}")
            edges.affects(sess, issue.id, affects)

        blocked_task = None
        if blocks:
            blocked_task = tasks.get_by_external_id(sess, blocks)
            if blocked_task is None:
                raise typer.BadParameter(f"no Task with external_id={blocks!r}")
            edges.blocks(sess, issue.id, blocked_task.id)
            tasks.update_fields(sess, blocked_task.id, workflow_status="blocked")

        found_during_task = None
        if found_during:
            found_during_task = tasks.get_by_external_id(sess, found_during)
            if found_during_task is None:
                raise typer.BadParameter(f"no Task with external_id={found_during!r}")
            edges.found_during(sess, issue.id, found_during_task.id)

    issue_file = IssueFile(
        issue_id=issue.id,
        reported_by=reported_by,
        found_during_task=found_during,
    )
    state_io.write_json(issue_file_path(root, issue.id), issue_file.model_dump(mode="json"))

    console.print(f"[green]Opened Issue[/green] {issue.id}: {title}")
    if affects:
        console.print(f"  AFFECTS {affects}")
    if blocked_task:
        console.print(f"  BLOCKS Task {blocks} (now workflow_status=blocked)")
    if found_during_task:
        console.print(f"  FOUND_DURING Task {found_during}")
