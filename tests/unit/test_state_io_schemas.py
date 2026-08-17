from __future__ import annotations

from reqgraph.state import io as state_io
from reqgraph.state.paths import task_file_path, todo_global_path
from reqgraph.state.schemas import TaskDecision, TaskFile, TodoGlobal


def test_todo_global_round_trip(project_root):
    original = TodoGlobal(project="demo", project_mode="greenfield", current_phase="phase-01")
    path = todo_global_path(project_root)
    state_io.write_json(path, original.model_dump(mode="json"))

    loaded = TodoGlobal.model_validate(state_io.read_json(path))
    assert loaded == original


def test_task_file_round_trip_with_nested_fields(project_root):
    original = TaskFile(id="task-01-01", title="Do the thing")
    original.decisions.append(TaskDecision(choice="use approach A", rationale="simpler"))
    path = task_file_path(project_root, "phase-01", "task-01-01")
    state_io.write_json(path, original.model_dump(mode="json"))

    loaded = TaskFile.model_validate(state_io.read_json(path))
    assert loaded.id == "task-01-01"
    assert loaded.decisions[0].choice == "use approach A"


def test_write_json_is_atomic_no_tmp_file_left_behind(project_root):
    path = project_root / "sub" / "file.json"
    state_io.write_json(path, {"a": 1})
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
