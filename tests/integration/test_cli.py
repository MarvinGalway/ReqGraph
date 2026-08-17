from __future__ import annotations

import json
import re
import sys

import pytest
from typer.testing import CliRunner

from reqgraph.cli.main import app
from reqgraph.graph.driver import session as graph_session
from reqgraph.graph.models import Task
from reqgraph.graph.repositories.task import TaskRepository
from reqgraph.llm.schemas import ClarificationDraft, CriticOutput

pytestmark = pytest.mark.integration

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_init_status_consistency_check_happy_path(neo4j_session):
    result = runner.invoke(app, ["init", "--project", "Demo"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "Demo" in result.output

    result = runner.invoke(app, ["consistency-check", "--strict"])
    assert result.exit_code == 0, result.output


def test_status_json_is_machine_parseable(neo4j_session):
    runner.invoke(app, ["init", "--project", "Demo", "--mode", "greenfield"])

    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["project"] == "Demo"
    assert payload["project_mode"] == "greenfield"
    assert payload["open_issues"] == 0
    assert "node_counts" in payload


def test_status_json_on_missing_project_is_still_valid_json(project_root):
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert "error" in payload


def test_ingest_requirements_then_run_critic_with_fake_llm(neo4j_session, fake_anthropic):
    runner.invoke(app, ["init", "--project", "Demo"])

    result = runner.invoke(
        app, ["ingest-requirements", "--text", "Users can cancel an order unless shipped."]
    )
    assert result.exit_code == 0, result.output
    match = re.search(r"Ingested Requirement ([0-9a-f-]+)", _strip_ansi(result.output))
    assert match is not None
    requirement_id = match.group(1)

    fake_anthropic(
        responses=[
            CriticOutput(
                clarifications=[ClarificationDraft(question="What counts as 'shipped'?", blocking=True)],
                summary="One blocking ambiguity found.",
            )
        ]
    )
    result = runner.invoke(app, ["run-critic", requirement_id])
    assert result.exit_code == 0, result.output
    assert "One blocking ambiguity found." in result.output

    with graph_session() as sess:
        record = sess.run(
            "MATCH (c:Clarification)-[:CLARIFIES]->(:Requirement {id: $id}) RETURN count(c) AS n",
            id=requirement_id,
        ).single()
        assert record["n"] == 1

    # formalize must refuse: the blocking clarification is unresolved
    result = runner.invoke(app, ["formalize", "--requirement-id", requirement_id])
    assert result.exit_code == 1
    assert "unresolved blocking" in _strip_ansi(result.output)


def _seed_bare_task(neo4j_session, external_id: str = "task-01-01") -> None:
    task = Task(title="do it", phase="phase-01")
    task.external_id = external_id
    TaskRepository().create(neo4j_session, task)


def test_run_task_verify_red_blocks_on_unexpected_pass(neo4j_session, target_repo):
    _seed_bare_task(neo4j_session)
    passing_command = f"{sys.executable} -c \"import sys; sys.exit(0)\""

    result = runner.invoke(
        app, ["run-task", "task-01-01", "--repo-path", str(target_repo), "--verify-red", "--test-command", passing_command]
    )
    assert result.exit_code == 1
    assert "expected the test command to FAIL" in _strip_ansi(result.output)


def test_run_task_verify_red_allow_pass_escape_hatch(neo4j_session, target_repo):
    _seed_bare_task(neo4j_session)
    passing_command = f"{sys.executable} -c \"import sys; sys.exit(0)\""

    result = runner.invoke(
        app,
        [
            "run-task",
            "task-01-01",
            "--repo-path",
            str(target_repo),
            "--verify-red",
            "--test-command",
            passing_command,
            "--allow-pass",
        ],
    )
    assert result.exit_code == 0, result.output


def test_run_task_verify_red_succeeds_on_expected_failure(neo4j_session, target_repo):
    _seed_bare_task(neo4j_session)
    failing_command = f"{sys.executable} -c \"import sys; sys.exit(1)\""

    result = runner.invoke(
        app, ["run-task", "task-01-01", "--repo-path", str(target_repo), "--verify-red", "--test-command", failing_command]
    )
    assert result.exit_code == 0, result.output
    assert "RED verified" in _strip_ansi(result.output)


def test_run_task_record_codeunit_is_idempotent(neo4j_session, target_repo):
    _seed_bare_task(neo4j_session)
    args = ["run-task", "task-01-01", "--repo-path", str(target_repo), "--record-codeunit", "orders.py:orders.cancel_order"]

    result1 = runner.invoke(app, args)
    assert result1.exit_code == 0, result1.output
    result2 = runner.invoke(app, args)
    assert result2.exit_code == 0, result2.output

    with graph_session() as sess:
        record = sess.run(
            "MATCH (c:CodeUnit {symbol: 'orders.cancel_order'})-[r:GENERATED_BY]->(:Task) RETURN count(r) AS n"
        ).single()
        assert record["n"] == 1
