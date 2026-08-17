from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.models import Task, TaskScope
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import contracts, issues, requirements
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import planner
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import PlannerOutput
from reqgraph.state import io as state_io
from reqgraph.state.paths import phase_todo_path, task_dir, task_file_path
from reqgraph.state.schemas import PhaseTaskRef, TaskFile, TaskScopeFile, TodoPhase


def _next_task_number(root, phase_id: str) -> int:
    tdir = task_dir(root, phase_id)
    if not tdir.exists():
        return 1
    existing = list(tdir.glob("task-*.json"))
    return len(existing) + 1


def run(
    contract_id: Annotated[str, typer.Option(help="Validated Contract id to derive Task(s) from")],
    phase: Annotated[str, typer.Option(help="Phase id, e.g. phase-01")] = "phase-01",
    issue_id: Annotated[str | None, typer.Option(help="Issue id this Task set addresses")] = None,
) -> None:
    root = project_root()
    with graph_session() as sess:
        contract = contracts.get(sess, contract_id)
        if contract is None:
            raise typer.BadParameter(f"no Contract with id={contract_id!r}")
        if contract.knowledge_status != "validated":
            console.print(
                f"[red]Refusing: Contract {contract_id} is not validated "
                f"(knowledge_status={contract.knowledge_status}). Run `validate` first.[/red]"
            )
            raise typer.Exit(code=1)

        requirement_ids = edges.outgoing_ids(sess, contract_id, "FORMALIZES")
        requirement = requirements.get(sess, requirement_ids[0]) if requirement_ids else None

        issue_summary = None
        if issue_id:
            issue = issues.get(sess, issue_id)
            if issue is None:
                raise typer.BadParameter(f"no Issue with id={issue_id!r}")
            issue_summary = f"{issue.title}: {issue.description}"

        contract_summary = (
            f"preconditions={contract.preconditions} postconditions={contract.postconditions} "
            f"acceptance={[a.model_dump() for a in contract.acceptance]}"
        )
        output: PlannerOutput = invoke_role(
            ROLES["planner"],
            planner.system_prompt(),
            planner.user_prompt(contract_summary, requirement.text if requirement else "", issue_summary),
            PlannerOutput,
        )

        created_ids: list[str] = []
        for draft in output.tasks:
            task = Task(
                title=draft.title,
                phase=phase,
                definition_of_done=draft.definition_of_done,
                scope=TaskScope(target_contracts=[contract_id], allowed_paths=draft.allowed_paths),
            )
            task_number = _next_task_number(root, phase) + len(created_ids)
            phase_num = phase.split("-")[-1]
            task.external_id = f"task-{phase_num}-{task_number:02d}"
            from reqgraph.graph.repositories.registry import tasks

            tasks.create(sess, task)
            edges.derives_from(sess, task.id, contract_id)
            if issue_id:
                edges.addresses(sess, task.id, issue_id)
            created_ids.append(task.external_id)

            task_file = TaskFile(
                id=task.external_id,
                title=draft.title,
                contract_refs=[contract_id],
                requirement_refs=requirement_ids,
                issues_addressed=[issue_id] if issue_id else [],
                scope=TaskScopeFile(allowed_paths=draft.allowed_paths),
            )
            state_io.write_json(task_file_path(root, phase, task.external_id), task_file.model_dump(mode="json"))

        todo_path = phase_todo_path(root, phase)
        if todo_path.exists():
            phase_data = TodoPhase.model_validate(state_io.read_json(todo_path))
        else:
            phase_data = TodoPhase(phase_id=phase)
        for ext_id, draft in zip(created_ids, output.tasks):
            phase_data.tasks.append(PhaseTaskRef(id=ext_id, title=draft.title))
        state_io.write_json(todo_path, phase_data.model_dump(mode="json"))

    console.print(f"[green]Derived {len(created_ids)} Task(s)[/green] from Contract {contract_id}:")
    for tid in created_ids:
        console.print(f"  - {tid}")
