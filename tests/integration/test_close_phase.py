from __future__ import annotations

import pytest
from typer.testing import CliRunner

from reqgraph.cli.main import app
from reqgraph.state import io as state_io
from reqgraph.state.paths import phase_todo_path, todo_global_path
from reqgraph.state.schemas import (
    LastRegression,
    OpenAssumption,
    PhaseTaskRef,
    TodoGlobal,
    TodoPhase,
)

pytestmark = pytest.mark.integration

runner = CliRunner()


def _write_phase(project_root, task_ids=("task-01-01",)):
    phase = TodoPhase(phase_id="phase-01", tasks=[PhaseTaskRef(id=t) for t in task_ids])
    state_io.write_json(phase_todo_path(project_root, "phase-01"), phase.model_dump(mode="json"))


def _write_global(project_root, **overrides):
    todo_global = TodoGlobal(project="Demo", **overrides)
    state_io.write_json(todo_global_path(project_root), todo_global.model_dump(mode="json"))


def test_close_phase_missing_phase_file(neo4j_session, project_root):
    result = runner.invoke(app, ["close-phase", "phase-99"])
    assert result.exit_code == 1
    assert "No phase todo file" in result.output


def test_close_phase_passes_when_everything_is_clean(neo4j_session, project_root):
    _write_phase(project_root)
    _write_global(project_root, last_regression=LastRegression(result="green"))

    result = runner.invoke(app, ["close-phase", "phase-01"])
    assert result.exit_code == 0, result.output
    assert "meets all exit criteria" in result.output


def test_close_phase_fails_on_blocking_assumption(neo4j_session, project_root):
    _write_phase(project_root)
    _write_global(
        project_root,
        last_regression=LastRegression(result="green"),
        open_assumptions=[OpenAssumption(assumption_id="a1", text="unclear rounding rule", blocking_tasks=["task-01-01"])],
    )

    result = runner.invoke(app, ["close-phase", "phase-01"])
    assert result.exit_code == 1
    assert "unclear rounding rule" in result.output


def test_close_phase_fails_when_regression_not_green(neo4j_session, project_root):
    _write_phase(project_root)
    _write_global(project_root, last_regression=LastRegression(result="red"))

    result = runner.invoke(app, ["close-phase", "phase-01"])
    assert result.exit_code == 1
    assert "target regression green" in result.output
