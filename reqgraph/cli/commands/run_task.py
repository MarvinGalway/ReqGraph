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

from reqgraph.cli.common import console, graph_session, project_root, resolve_test_command
from reqgraph.exec.test_runner import run_test_command
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
    verify_red: Annotated[
        bool, typer.Option("--verify-red", help="Run the test command; require it to FAIL (spec G3 step 3)")
    ] = False,
    test_command: Annotated[
        str | None, typer.Option(help="Overrides project.json's stored test_command for --verify-red")
    ] = None,
    allow_pass: Annotated[
        bool, typer.Option("--allow-pass", help="Don't error if --verify-red unexpectedly observes a pass")
    ] = False,
) -> None:
    record_codeunit = record_codeunit or []
    record_configunit = record_configunit or []
    record_test = record_test or []
    root = project_root()

    if verify_red:
        command = resolve_test_command(root, test_command)
        result = run_test_command(repo_path, command)
        if result.passed and not allow_pass:
            console.print(
                f"[red]--verify-red expected the test command to FAIL, but it passed.[/red]\n"
                f"  command: {command}\n"
                "  This usually means the new test doesn't actually exercise the new behavior yet. "
                "Pass --allow-pass if this is intentional."
            )
            raise typer.Exit(code=1)
        console.print(
            f"[green]RED verified[/green] — {command!r} exited {result.exit_code} "
            f"({'unexpected pass, allowed' if result.passed else 'failed as expected'})."
        )

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
            if not edges.edge_exists(sess, "GENERATED_BY", node.id, task.id):
                edges.generated_by(sess, node.id, task.id)
            for contract_id in task.scope.target_contracts:
                if not edges.edge_exists(sess, "IMPLEMENTS", node.id, contract_id):
                    edges.implements(sess, node.id, contract_id)
            recorded.append(f"CodeUnit {node.path}::{node.symbol} id={node.id}")

        for ref in record_test:
            path, symbol = _split(ref)
            source = (repo_path / path).read_text(encoding="utf-8")
            extraction = PythonExtractor().extract(path, source)
            match = next((t for t in extraction.tests if t.symbol == symbol), None)
            if match is None:
                raise typer.BadParameter(f"test symbol {symbol!r} not found in {path}")
            test_node = tests.find_by_path_symbol(sess, path, symbol)
            if test_node is None:
                test_node = Test(path=path, symbol=symbol, framework=match.framework, created_by="human")
                tests.create(sess, test_node)
            if not edges.edge_exists(sess, "GENERATED_BY", test_node.id, task.id):
                edges.generated_by(sess, test_node.id, task.id)
            for contract_id in task.scope.target_contracts:
                if not edges.edge_exists(sess, "TESTS", test_node.id, contract_id):
                    edges.tests(sess, test_node.id, contract_id)
            recorded.append(f"Test {test_node.path}::{test_node.symbol} id={test_node.id}")

    root_task_file = task_file_path(root, task.phase or "phase-01", task_id)
    if root_task_file.exists():
        data = TaskFile.model_validate(state_io.read_json(root_task_file))
        data.status = "in_progress"
        if verify_red:
            data.tdd_loop_state.tests_verified_red = True
            data.tdd_loop_state.step = "verify-red"
        if step:
            data.tdd_loop_state.step = step  # type: ignore[assignment]
        data.artifacts_generated.codeunits.extend(
            ref for ref in record_codeunit if ref not in data.artifacts_generated.codeunits
        )
        data.artifacts_generated.tests.extend(
            ref for ref in record_test if ref not in data.artifacts_generated.tests
        )
        data.artifacts_generated.configunits.extend(
            ref for ref in record_configunit if ref not in data.artifacts_generated.configunits
        )
        state_io.write_json(root_task_file, data.model_dump(mode="json"))

    console.print(f"[green]Task {task_id} -> in_progress[/green]")
    for r in recorded:
        console.print(f"  recorded {r}")
    if step:
        console.print(f"  tdd_loop_state.step = {step}")
