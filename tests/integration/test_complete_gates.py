from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reqgraph.cli.main import app
from reqgraph.graph.models import CodeUnit, Contract, Requirement, Task, TaskScope
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.codeunit import CodeUnitRepository
from reqgraph.graph.repositories.contract import ContractRepository
from reqgraph.graph.repositories.requirement import RequirementRepository
from reqgraph.graph.repositories.task import TaskRepository
from reqgraph.llm.schemas import ReviewerOutput
from reqgraph.state import io as state_io
from reqgraph.state.paths import impact_dir, project_json_path, task_file_path, todo_global_path
from reqgraph.state.schemas import ArtifactsGenerated, ProjectFile, TaskFile, TodoGlobal

pytestmark = pytest.mark.integration

runner = CliRunner()

FIXTURE_REPO = Path(__file__).parent.parent / "fixtures" / "sample_repo"


def _seed_task(neo4j_session, project_root: Path, *, record_codeunit: bool) -> str:
    req = Requirement(text="Users can cancel an order unless it has already shipped.")
    RequirementRepository().create(neo4j_session, req)

    contract = Contract(
        preconditions=["order exists"],
        postconditions=["order.status == 'cancelled'"],
        knowledge_status="validated",
    )
    ContractRepository().create(neo4j_session, contract)
    edges.formalizes(neo4j_session, contract.id, req.id, generated_by="human")

    task = Task(title="Implement cancel_order", phase="phase-01", scope=TaskScope(target_contracts=[contract.id]))
    task.external_id = "task-01-01"
    TaskRepository().create(neo4j_session, task)
    edges.derives_from(neo4j_session, task.id, contract.id)

    artifacts = ArtifactsGenerated()
    if record_codeunit:
        codeunit = CodeUnit(path="orders.py", symbol="orders.cancel_order", kind="function", hash="deadbeef")
        CodeUnitRepository().create(neo4j_session, codeunit)
        edges.implements(neo4j_session, codeunit.id, contract.id)
        edges.generated_by(neo4j_session, codeunit.id, task.id)
        artifacts.codeunits.append("orders.py:orders.cancel_order")

    task_file = TaskFile(id="task-01-01", title="Implement cancel_order", artifacts_generated=artifacts)
    state_io.write_json(task_file_path(project_root, "phase-01", "task-01-01"), task_file.model_dump(mode="json"))

    state_io.write_json(
        project_json_path(project_root), ProjectFile(project="Demo").model_dump(mode="json")
    )
    state_io.write_json(todo_global_path(project_root), TodoGlobal(project="Demo").model_dump(mode="json"))
    return "task-01-01"


def test_complete_fails_with_no_artifacts(neo4j_session, project_root, target_repo):
    task_id = _seed_task(neo4j_session, project_root, record_codeunit=False)
    result = runner.invoke(app, ["complete", task_id, "--repo-path", str(target_repo), "--test-command", "true"])
    assert result.exit_code == 1
    assert "no artifacts recorded" in result.output


def test_complete_fails_without_impact_check(neo4j_session, project_root, target_repo):
    task_id = _seed_task(neo4j_session, project_root, record_codeunit=True)
    result = runner.invoke(app, ["complete", task_id, "--repo-path", str(target_repo), "--test-command", "true"])
    assert result.exit_code == 1
    assert "impact not checked" in result.output


def _write_impact_audit(project_root: Path, target_id: str) -> None:
    directory = impact_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    state_io.write_json(directory / "impact-20260101T000000.json", {"target_id": target_id})


def test_complete_fails_on_regression(neo4j_session, project_root, target_repo):
    task_id = _seed_task(neo4j_session, project_root, record_codeunit=True)
    node = CodeUnitRepository().find_current(neo4j_session, "orders.py", "orders.cancel_order")
    _write_impact_audit(project_root, node.id)

    failing_command = f"{sys.executable} -c \"import sys; sys.exit(1)\""
    result = runner.invoke(app, ["complete", task_id, "--repo-path", str(target_repo), "--test-command", failing_command])
    assert result.exit_code == 1
    assert "regression FAILED" in result.output


def test_complete_fails_on_reviewer_verdict(neo4j_session, project_root, target_repo, fake_anthropic):
    task_id = _seed_task(neo4j_session, project_root, record_codeunit=True)
    node = CodeUnitRepository().find_current(neo4j_session, "orders.py", "orders.cancel_order")
    _write_impact_audit(project_root, node.id)
    fake_anthropic(
        responses=[
            ReviewerOutput(
                verdict="fail",
                contract_fidelity_notes="doesn't check shipped status",
                requirement_fidelity_notes="misses shipped guard",
                concerns=["cancel_order does not raise when order is shipped"],
            )
        ]
    )

    passing_command = f"{sys.executable} -c \"import sys; sys.exit(0)\""
    result = runner.invoke(app, ["complete", task_id, "--repo-path", str(target_repo), "--test-command", passing_command])
    assert result.exit_code == 1
    assert "Reviewer verdict: FAIL" in result.output


def test_complete_succeeds_end_to_end(neo4j_session, project_root, target_repo, fake_anthropic):
    task_id = _seed_task(neo4j_session, project_root, record_codeunit=True)
    node = CodeUnitRepository().find_current(neo4j_session, "orders.py", "orders.cancel_order")
    _write_impact_audit(project_root, node.id)
    fake_anthropic(
        responses=[
            ReviewerOutput(
                verdict="pass",
                contract_fidelity_notes="matches contract",
                requirement_fidelity_notes="matches requirement",
                concerns=[],
            )
        ]
    )

    result = runner.invoke(app, ["complete", task_id, "--repo-path", str(target_repo), "--test-command", "pytest -q"])
    assert result.exit_code == 0, result.output
    assert "-> done" in result.output

    task = TaskRepository().get_by_external_id(neo4j_session, task_id)
    assert task.workflow_status == "done"

    todo_global = TodoGlobal.model_validate(state_io.read_json(todo_global_path(project_root)))
    assert todo_global.last_regression.result == "green"
