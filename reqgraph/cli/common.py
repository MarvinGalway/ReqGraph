"""Shared helpers for CLI command modules: a Rich console, project-root
resolution, and thin wrappers around the graph session so every command
follows the same (a) load state, (b) touch graph, (c) touch LLM,
(d) save state, (e) print summary shape.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from reqgraph.config import get_settings
from reqgraph.graph.driver import session as graph_session
from reqgraph.state import io as state_io
from reqgraph.state.paths import project_json_path
from reqgraph.state.schemas import ProjectFile

# soft_wrap=True: Rich otherwise hard-wraps long lines at a default width
# (80 cols) whenever stdout isn't a real terminal — i.e. exactly when an
# external agent pipes graph-cli's output to parse it (see
# docs/AGENT_INTEGRATION.md). A wrapped line silently breaks any regex/split
# looking for a trailing token like an echoed node id. Human terminal
# rendering is unaffected — this only stops Rich from inserting hard
# newlines that aren't there in a real wide terminal.
console = Console(soft_wrap=True)


def project_root() -> Path:
    return get_settings().reqgraph_project_root.resolve()


def resolve_test_command(root: Path, override: str | None) -> str:
    """Used by `run-task --verify-red` and `complete`'s regression gate.
    Explicit --test-command always wins; otherwise falls back to
    project.json's stored test_command from `init --test-command`.
    """
    if override:
        return override
    path = project_json_path(root)
    if path.exists():
        project_file = ProjectFile.model_validate(state_io.read_json(path))
        if project_file.test_command:
            return project_file.test_command
    raise typer.BadParameter(
        "no test command configured — pass --test-command or run "
        "`graph-cli init --test-command '...'`"
    )


__all__ = ["console", "graph_session", "project_root", "resolve_test_command"]
