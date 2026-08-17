from __future__ import annotations

import json
from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.context import task_context


def run(
    task_id: str,
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON instead of Markdown")] = False,
    max_tokens: Annotated[int, typer.Option(help="Context token budget")] = 12000,
) -> None:
    root = project_root()
    with graph_session() as sess:
        try:
            ctx = task_context.assemble(sess, root, task_id, max_tokens=max_tokens)
        except task_context.TaskNotFoundError as e:
            raise typer.BadParameter(str(e)) from e

    if as_json:
        console.print_json(json.dumps(task_context.render_json(ctx)))
    else:
        console.print(task_context.render_markdown(ctx))
