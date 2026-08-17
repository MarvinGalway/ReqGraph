"""Shared helpers for CLI command modules: a Rich console, project-root
resolution, and thin wrappers around the graph session so every command
follows the same (a) load state, (b) touch graph, (c) touch LLM,
(d) save state, (e) print summary shape.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from reqgraph.config import get_settings
from reqgraph.graph.driver import session as graph_session

console = Console()


def project_root() -> Path:
    return get_settings().reqgraph_project_root.resolve()


__all__ = ["console", "graph_session", "project_root"]
