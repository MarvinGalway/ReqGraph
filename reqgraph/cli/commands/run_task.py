"""`run-task <task-id>` — lifecycle recorder, not an autonomous coder (see
implementation plan). It transitions the Task to in_progress and, as the
human/agent doing the actual implementation reports finished artifacts,
records them into the graph by re-running the same Python-AST extractor
`bootstrap-scan` uses against the target file on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.extract.python_ast import PythonExtractor
from reqgraph.graph.models import CodeUnit, Test
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import codeunits, tasks, tests
from reqgraph.state import io as state_io
from reqgraph.state.paths import task_file_path
from reqgraph.state.schemas import TaskFile


def _split(ref: str) -> tuple[str, str]:
    if ":" not in ref:
        raise typer.BadParameter(f"expected 'path:symbol', got {ref!r}")
    path, symbol = ref.split(":", 1)
    return path, symbol


def run(
    task_id: str,
    repo_path: Annotated[Path, typer.Option(help="Root of the target repository the artifacts live in")] = Path("."),
    record_codeunit: Annotated[list[str] | None, typer.Option(help="path:symbol, repeatable")] = None,
    record_configunit: Annotated[
        list[str] | None, typer.Option(help="path:key, repeatable (not extracted from disk)")
    ] = None,
    record_test: Annotated[list[str] | None, typer.Option(help="path:symbol, repeatable")] = None,
    step: Annotated[str | None, typer.Option(help="tdd_loop_state.step to record")] = None,
) -> None:
    record_codeunit = record_codeunit or []
    record_configunit = record_configunit or []
    record_test = record_test or []
    root = project_root()
    with graph_session() as sess:
        task = tasks.get_by_external_id(sess, task_id)
        if task is None:
            raise typer.BadParameter(f"no Task with external_id={task_id!r}")
        tasks.update_fields(sess, task.id, workflow_status="in_progress")

        recorded: list[str] = []
        for ref in record_codeunit:
            path, symbol = _split(ref)
            source = (repo_path / path).read_text(encoding="utf-8")
            extraction = PythonExtractor().extract(path, source)
            match = next((c for c in extraction.codeunits if c.symbol == symbol), None)
            if match is None:
                raise typer.BadParameter(f"symbol {symbol!r} not found in {path}")
            existing = codeunits.find_current(sess, path, symbol)
            if existing and existing.hash == match.hash:
                node = existing
            else:
                node = CodeUnit(path=path, symbol=symbol, kind=match.kind, hash=match.hash, created_by="human")
                if existing:
                    codeunits.create_version(sess, node, existing.id)
                else:
                    codeunits.create(sess, node)
            edges.generated_by(sess, node.id, task.id)
            for contract_id in task.scope.target_contracts:
                edges.implements(sess, node.id, contract_id)
            recorded.append(f"CodeUnit {node.path}::{node.symbol}")

        for ref in record_test:
            path, symbol = _split(ref)
            source = (repo_path / path).read_text(encoding="utf-8")
            extraction = PythonExtractor().extract(path, source)
            match = next((t for t in extraction.tests if t.symbol == symbol), None)
            if match is None:
                raise typer.BadParameter(f"test symbol {symbol!r} not found in {path}")
            test_node = Test(path=path, symbol=symbol, framework=match.framework, created_by="human")
            tests.create(sess, test_node)
            edges.generated_by(sess, test_node.id, task.id)
            for contract_id in task.scope.target_contracts:
                edges.tests(sess, test_node.id, contract_id)
            recorded.append(f"Test {test_node.path}::{test_node.symbol}")

    root_task_file = task_file_path(root, task.phase or "phase-01", task_id)
    if root_task_file.exists():
        data = TaskFile.model_validate(state_io.read_json(root_task_file))
        data.status = "in_progress"
        if step:
            data.tdd_loop_state.step = step  # type: ignore[assignment]
        data.artifacts_generated.codeunits.extend(record_codeunit)
        data.artifacts_generated.tests.extend(record_test)
        data.artifacts_generated.configunits.extend(record_configunit)
        state_io.write_json(root_task_file, data.model_dump(mode="json"))

    console.print(f"[green]Task {task_id} -> in_progress[/green]")
    for r in recorded:
        console.print(f"  recorded {r}")
    if step:
        console.print(f"  tdd_loop_state.step = {step}")
