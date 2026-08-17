"""`context <task-id>` assembly — spec §10.1 + models-config-v0.2.json's
`task_traversal_rules`/`context_budget_quotas`. Pure typed traversal, no
vector entry point needed (the task is already concrete). Never writes to
the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from neo4j import Session

from reqgraph.context.budget import PRIORITY_BY_KNOWLEDGE_STATUS, BudgetItem, allocate
from reqgraph.context.labels import status_label
from reqgraph.graph.models import Task
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import (
    codeunits,
    configunits,
    contracts,
    examples,
    issues,
    requirements,
    tasks,
    tests,
)
from reqgraph.state import io as state_io
from reqgraph.state.paths import issue_file_path, phase_todo_path, task_file_path


class TaskNotFoundError(RuntimeError):
    pass


@dataclass
class TaskContext:
    task: Task
    items: list[BudgetItem] = field(default_factory=list)


def _priority(knowledge_status: str) -> int:
    return PRIORITY_BY_KNOWLEDGE_STATUS.get(knowledge_status, 2)


def assemble(
    sess: Session, project_root: Path, task_external_id: str, max_tokens: int = 12000
) -> TaskContext:
    task = tasks.get_by_external_id(sess, task_external_id)
    if task is None:
        raise TaskNotFoundError(f"no Task with external_id={task_external_id!r}")

    raw: list[BudgetItem] = []

    # Task -> Contract -> Requirement
    contract_ids = edges.outgoing_ids(sess, task.id, "DERIVES_FROM")
    for cid in contract_ids:
        contract = contracts.get(sess, cid)
        if contract is None:
            continue
        raw.append(
            BudgetItem(
                "contracts_and_requirements",
                f"{status_label(contract.knowledge_status)} Contract {contract.id}: "
                f"pre={contract.preconditions} post={contract.postconditions} "
                f"acceptance={[a.model_dump() for a in contract.acceptance]}",
                priority=_priority(contract.knowledge_status),
            )
        )
        for rid in edges.outgoing_ids(sess, contract.id, "FORMALIZES"):
            requirement = requirements.get(sess, rid)
            if requirement is None:
                continue
            raw.append(
                BudgetItem(
                    "contracts_and_requirements",
                    f"{status_label(requirement.knowledge_status)} Requirement {requirement.id}: "
                    f"{requirement.text}",
                    priority=_priority(requirement.knowledge_status),
                )
            )
        # validated Examples witnessing this contract
        for eid in edges.incoming_ids(sess, contract.id, "WITNESSES"):
            example = examples.get(sess, eid)
            if example is None or example.knowledge_status != "validated":
                continue
            raw.append(
                BudgetItem(
                    "validated_examples",
                    f"{status_label(example.knowledge_status)} Example {example.id}: "
                    f"input={example.input} -> expected={example.expected_output} "
                    f"edge_case={example.edge_case}",
                    priority=_priority(example.knowledge_status),
                )
            )
        # CodeUnit/ConfigUnit implementing/constraining this contract
        for cu_id in edges.incoming_ids(sess, contract.id, "IMPLEMENTS"):
            cu = codeunits.get(sess, cu_id)
            if cu is None:
                continue
            raw.append(
                BudgetItem(
                    "implementation_and_dependency_interfaces",
                    f"{status_label(cu.knowledge_status, cu.verification_status)} "
                    f"CodeUnit {cu.path}::{cu.symbol}",
                    priority=_priority(cu.knowledge_status),
                )
            )
        for cfg_id in edges.incoming_ids(sess, contract.id, "CONSTRAINS"):
            cfg = configunits.get(sess, cfg_id)
            if cfg is None:
                continue
            raw.append(
                BudgetItem(
                    "implementation_and_dependency_interfaces",
                    f"{status_label(cfg.knowledge_status, cfg.verification_status)} "
                    f"ConfigUnit {cfg.path}::{cfg.key}",
                    priority=_priority(cfg.knowledge_status),
                )
            )

    # Task -> Issue (ADDRESSES) and Issue -> Task (BLOCKS)
    addressed_issue_ids = edges.outgoing_ids(sess, task.id, "ADDRESSES")
    blocking_issue_ids = edges.incoming_ids(sess, task.id, "BLOCKS")
    for iid in set(addressed_issue_ids) | set(blocking_issue_ids):
        issue = issues.get(sess, iid)
        if issue is None:
            continue
        raw.append(
            BudgetItem(
                "constraints_assumptions_issues",
                f"{status_label(issue.knowledge_status)} Issue {issue.id} "
                f"[{issue.workflow_status}/{issue.classification}]: {issue.title}",
                priority=0 if iid in blocking_issue_ids else 1,
            )
        )

    # Artifacts generated during this task
    for label, repo in (("CodeUnit", codeunits), ("ConfigUnit", configunits), ("Test", tests)):
        for artifact_id in edges.incoming_ids(sess, task.id, "GENERATED_BY"):
            artifact = repo.get(sess, artifact_id)
            if artifact is None:
                continue
            desc = f"{status_label(artifact.knowledge_status, artifact.verification_status)} {label} {artifact.id}"
            raw.append(
                BudgetItem("implementation_and_dependency_interfaces", desc, priority=_priority(artifact.knowledge_status))
            )
            # 1-hop DEPENDS_ON from target artifacts
            for dep_id in edges.outgoing_ids(sess, artifact_id, "DEPENDS_ON"):
                raw.append(
                    BudgetItem(
                        "implementation_and_dependency_interfaces",
                        f"{label} {artifact.id} DEPENDS_ON {dep_id}",
                        priority=3,
                    )
                )

    # scope targets (even if not yet linked via GENERATED_BY)
    for cu_id in task.scope.target_codeunits:
        cu = codeunits.get(sess, cu_id)
        if cu is not None:
            raw.append(
                BudgetItem(
                    "implementation_and_dependency_interfaces",
                    f"(in scope) CodeUnit {cu.path}::{cu.symbol}",
                    priority=1,
                )
            )

    # project-state: task file, phase todo, blocking issue files
    tfp = _find_task_file(project_root, task_external_id)
    if tfp is not None and tfp.exists():
        data = state_io.read_json(tfp)
        raw.append(
            BudgetItem(
                "state_todo_decisions",
                f"Task file: status={data.get('status')} tdd_step={data.get('tdd_loop_state', {}).get('step')} "
                f"decisions={data.get('decisions')}",
                priority=0,
            )
        )
        phase_id = _phase_of(task_external_id)
        todo_path = phase_todo_path(project_root, phase_id)
        if todo_path.exists():
            phase_data = state_io.read_json(todo_path)
            raw.append(
                BudgetItem(
                    "state_todo_decisions",
                    f"Phase {phase_id}: goal={phase_data.get('goal')} exit_criteria={phase_data.get('exit_criteria')}",
                    priority=1,
                )
            )
        for finding in data.get("out_of_scope_findings", []):
            issue_id = finding.get("issue_id")
            issue_path = issue_file_path(project_root, issue_id) if issue_id else None
            if issue_path and issue_path.exists():
                issue_data = state_io.read_json(issue_path)
                raw.append(
                    BudgetItem(
                        "constraints_assumptions_issues",
                        f"Blocking Issue file {issue_id}: {issue_data.get('workflow_status')}",
                        priority=0,
                    )
                )

    allocated = allocate(raw, max_tokens)
    return TaskContext(task=task, items=allocated)


def _phase_of(task_external_id: str) -> str:
    parts = task_external_id.split("-")
    return f"phase-{parts[1]}" if len(parts) >= 2 else "phase-01"


def _find_task_file(project_root: Path, task_external_id: str) -> Path | None:
    phase_id = _phase_of(task_external_id)
    return task_file_path(project_root, phase_id, task_external_id)


def render_markdown(ctx: TaskContext) -> str:
    lines = [f"# Task context: {ctx.task.external_id} ({ctx.task.title})", ""]
    by_category: dict[str, list[BudgetItem]] = {}
    for item in ctx.items:
        by_category.setdefault(item.category, []).append(item)
    for category, category_items in by_category.items():
        lines.append(f"## {category}")
        for item in category_items:
            lines.append(f"- {item.text}")
        lines.append("")
    return "\n".join(lines)


def render_json(ctx: TaskContext) -> dict:
    return {
        "task_id": ctx.task.external_id,
        "task_title": ctx.task.title,
        "items": [{"category": i.category, "text": i.text} for i in ctx.items],
    }
