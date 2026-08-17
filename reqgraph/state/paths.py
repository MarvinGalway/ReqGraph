"""Path resolution for /.project-state/, per spec §11's file tree.

    /.project-state/
      project.json
      todo-global.json
      issues/issue-<id>.json
      bootstrap/bootstrap-state.json
      phases/phase-NN/todo-phase.json
      phases/phase-NN/tasks/task-NN-NN.json
      decisions-log.md
      impact/impact-<ts>.json   (extension — audit trail for `impact`, not in the spec's tree)
"""

from __future__ import annotations

from pathlib import Path


def state_root(project_root: Path) -> Path:
    return project_root / ".project-state"


def project_json_path(project_root: Path) -> Path:
    return state_root(project_root) / "project.json"


def todo_global_path(project_root: Path) -> Path:
    return state_root(project_root) / "todo-global.json"


def decisions_log_path(project_root: Path) -> Path:
    return state_root(project_root) / "decisions-log.md"


def issues_dir(project_root: Path) -> Path:
    return state_root(project_root) / "issues"


def issue_file_path(project_root: Path, issue_id: str) -> Path:
    return issues_dir(project_root) / f"issue-{issue_id}.json"


def bootstrap_state_path(project_root: Path) -> Path:
    return state_root(project_root) / "bootstrap" / "bootstrap-state.json"


def phases_dir(project_root: Path) -> Path:
    return state_root(project_root) / "phases"


def phase_dir(project_root: Path, phase_id: str) -> Path:
    return phases_dir(project_root) / phase_id


def phase_todo_path(project_root: Path, phase_id: str) -> Path:
    return phase_dir(project_root, phase_id) / "todo-phase.json"


def task_dir(project_root: Path, phase_id: str) -> Path:
    return phase_dir(project_root, phase_id) / "tasks"


def task_file_path(project_root: Path, phase_id: str, task_id: str) -> Path:
    return task_dir(project_root, phase_id) / f"{task_id}.json"


def impact_dir(project_root: Path) -> Path:
    return state_root(project_root) / "impact"
