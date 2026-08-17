"""`complete <task-id>` — the real Definition-of-Done gate (spec G3 steps
7-10). Four automated checks, all fail-closed and rerunnable with no side
effects on failure: artifacts recorded, impact-check enforced, regression
suite actually run, and a Reviewer LLM verdict on Code/Contract/Requirement
fidelity. Nothing here writes code — Codegen stays an external agent; this
command only verifies what it produced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root, resolve_test_command
from reqgraph.exec.test_runner import run_test_command
from reqgraph.extract.python_ast import extract_symbol_source
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import (
    codeunits,
    configunits,
    contracts,
    requirements,
    tasks,
)
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import reviewer as reviewer_prompt
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import ReviewerOutput
from reqgraph.state import io as state_io
from reqgraph.state.paths import (
    decisions_log_path,
    impact_dir,
    phase_todo_path,
    task_file_path,
    todo_global_path,
)
from reqgraph.state.schemas import LastRegression, TaskFile, TodoGlobal, TodoPhase


def _impact_checked_ids(root: Path) -> set[str]:
    checked: set[str] = set()
    directory = impact_dir(root)
    if not directory.exists():
        return checked
    for audit_file in directory.glob("impact-*.json"):
        data = json.loads(audit_file.read_text(encoding="utf-8"))
        target_id = data.get("target_id")
        if target_id:
            checked.add(target_id)
    return checked


def run(
    task_id: str,
    repo_path: Annotated[Path, typer.Option(help="Root of the target repository the artifacts live in")] = Path("."),
    test_command: Annotated[str | None, typer.Option(help="Overrides project.json's stored test_command")] = None,
) -> None:
    root = project_root()

    with graph_session() as sess:
        task = tasks.get_by_external_id(sess, task_id)
        if task is None:
            raise typer.BadParameter(f"no Task with external_id={task_id!r}")
        phase = task.phase or "phase-01"
        task_file_p = task_file_path(root, phase, task_id)
        if not task_file_p.exists():
            raise typer.BadParameter(f"no task file at {task_file_p}")
        data = TaskFile.model_validate(state_io.read_json(task_file_p))

        failures: list[str] = []
        artifacts = data.artifacts_generated
        if not (artifacts.codeunits or artifacts.configunits or artifacts.tests):
            failures.append("no artifacts recorded (run `run-task --record-...` first)")

        # --- Gate 2: impact-check enforced (DoD's impact_check field) ---
        target_ids: list[str] = []
        for ref in artifacts.codeunits:
            path, symbol = ref.split(":", 1)
            codeunit_node = codeunits.find_current(sess, path, symbol)
            if codeunit_node:
                target_ids.append(codeunit_node.id)
        for ref in artifacts.configunits:
            path, key = ref.split(":", 1)
            configunit_node = configunits.find_current(sess, path, key)
            if configunit_node:
                target_ids.append(configunit_node.id)
        if target_ids:
            checked = _impact_checked_ids(root)
            missing = [t for t in target_ids if t not in checked]
            if missing:
                failures.append(
                    f"impact not checked for {len(missing)} artifact(s) — run `graph-cli impact <id>` "
                    f"first: {', '.join(missing)}"
                )

        if failures:
            _report_and_exit(task_id, failures)

        # --- Gate 3: regression ---
        command = resolve_test_command(root, test_command)
        result = run_test_command(repo_path, command)
        if not result.passed:
            failures.append(f"regression FAILED: {command!r} exited {result.exit_code}\n{result.stderr[-1000:]}")
            _report_and_exit(task_id, failures)

        # --- Gate 4: reviewer fidelity ---
        contract_texts = []
        requirement_texts: set[str] = set()
        for contract_id in task.scope.target_contracts:
            contract = contracts.get(sess, contract_id)
            if contract is None:
                continue
            contract_texts.append(
                f"[{contract.id}] preconditions={contract.preconditions} "
                f"postconditions={contract.postconditions} invariants={contract.invariants} "
                f"acceptance={[a.model_dump() for a in contract.acceptance]}"
            )
            for req_id in edges.outgoing_ids(sess, contract.id, "FORMALIZES"):
                requirement = requirements.get(sess, req_id)
                if requirement:
                    requirement_texts.add(requirement.text)

        codeunit_sources = _gather_sources(repo_path, artifacts.codeunits)
        test_sources = _gather_sources(repo_path, artifacts.tests)

        review: ReviewerOutput = invoke_role(
            ROLES["reviewer"],
            reviewer_prompt.system_prompt(),
            reviewer_prompt.user_prompt(
                "\n".join(contract_texts), "\n".join(requirement_texts), codeunit_sources, test_sources
            ),
            ReviewerOutput,
        )
        if review.verdict != "pass":
            failures.append("Reviewer verdict: FAIL — " + "; ".join(review.concerns or [review.requirement_fidelity_notes]))
            _report_and_exit(task_id, failures)

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

    global_path = todo_global_path(root)
    if global_path.exists():
        todo_global = TodoGlobal.model_validate(state_io.read_json(global_path))
        todo_global.last_regression = LastRegression(result="green")
        state_io.write_json(global_path, todo_global.model_dump(mode="json"))

    state_io.append_text(
        decisions_log_path(root), f"- Task {task_id} completed (regression=green, reviewer=pass).\n"
    )
    console.print(f"[green]Task {task_id} -> done[/green] (regression green, reviewer pass)")
    console.print(f"  reviewer notes: {review.contract_fidelity_notes}")


def _gather_sources(repo_path: Path, refs: list[str]) -> list[str]:
    sources = []
    for ref in refs:
        path, symbol = ref.split(":", 1)
        file_path = repo_path / path
        if not file_path.exists():
            continue
        source = extract_symbol_source(path, file_path.read_text(encoding="utf-8"), symbol)
        if source:
            sources.append(f"# {ref}\n{source}")
    return sources


def _report_and_exit(task_id: str, failures: list[str]) -> None:
    console.print(f"[red]Cannot complete {task_id}, Definition of Done not met:[/red]")
    for f in failures:
        console.print(f"  - {f}")
    raise typer.Exit(code=1)
