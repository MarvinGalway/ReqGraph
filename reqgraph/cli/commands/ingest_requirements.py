from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session
from reqgraph.graph.models import Requirement
from reqgraph.graph.repositories.registry import requirements


def run(
    text: Annotated[str | None, typer.Option(help="Requirement prose, given inline")] = None,
    file: Annotated[Path | None, typer.Option(help="Path to a file containing the requirement prose")] = None,
    source: Annotated[str, typer.Option(help="person | document | ticket | reverse-engineered")] = "person",
) -> None:
    if text:
        body = text
    elif file:
        body = file.read_text(encoding="utf-8")
    else:
        raise typer.BadParameter("provide either --text or --file")

    requirement = Requirement(text=body, source=source, origin_mode="greenfield")
    with graph_session() as sess:
        requirements.create(sess, requirement)

    console.print(f"[green]Ingested Requirement[/green] {requirement.id}")
    console.print(f"  {body[:120]}{'...' if len(body) > 120 else ''}")
