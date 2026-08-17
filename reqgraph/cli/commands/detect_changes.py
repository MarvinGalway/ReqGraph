"""`detect-changes <repo-path>` — spec §9.2, symbol-level via git diff + AST
re-extraction. Never touches Requirement/Contract.knowledge_status; only
sets verification_status=needs_revalidation on the new technical version.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.extract.git_diff import changed_files, current_revision, read_file_at_revision
from reqgraph.extract.python_ast import PythonExtractor
from reqgraph.graph.models import CodeUnit
from reqgraph.graph.repositories.registry import codeunits
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState


def run(
    repo_path: Path,
    since: Annotated[str | None, typer.Option(help="Old revision; default: last recorded bootstrap revision")] = None,
) -> None:
    root = project_root()
    bootstrap_path = bootstrap_state_path(root)
    old_rev = since
    if old_rev is None and bootstrap_path.exists():
        old_rev = state_io.read_json(bootstrap_path).get("repository_revision") or None
    if not old_rev:
        raise typer.BadParameter("no baseline revision known — pass --since <rev>")

    new_rev = current_revision(repo_path)
    files = changed_files(repo_path, old_rev, new_rev)
    py_files = [f for f in files if f.endswith(".py")]

    extractor = PythonExtractor()
    changed_symbols: list[tuple[str, str]] = []
    new_symbols: list[tuple[str, str]] = []

    with graph_session() as sess:
        for path in py_files:
            old_source = read_file_at_revision(repo_path, old_rev, path) or ""
            new_source = (repo_path / path).read_text(encoding="utf-8") if (repo_path / path).exists() else ""

            old_map = {u.symbol: u.hash for u in extractor.extract(path, old_source).codeunits} if old_source else {}
            new_result = extractor.extract(path, new_source) if new_source else None
            new_map = {u.symbol: u for u in new_result.codeunits} if new_result else {}

            for symbol, unit in new_map.items():
                old_hash = old_map.get(symbol)
                if old_hash is None:
                    existing = codeunits.find_current(sess, path, symbol)
                    if existing is not None:
                        continue  # already known from a prior scan, not actually new
                    node = CodeUnit(
                        path=path, symbol=symbol, kind=unit.kind, hash=unit.hash, created_by="static-analysis"
                    )
                    codeunits.create(sess, node)
                    new_symbols.append((path, symbol))
                elif old_hash != unit.hash:
                    existing = codeunits.find_current(sess, path, symbol)
                    node = CodeUnit(
                        path=path,
                        symbol=symbol,
                        kind=unit.kind,
                        hash=unit.hash,
                        created_by="static-analysis",
                        verification_status="needs_revalidation",
                    )
                    if existing is not None:
                        codeunits.create_version(sess, node, existing.id)
                    else:
                        codeunits.create(sess, node)
                    changed_symbols.append((path, symbol))

    if bootstrap_path.exists():
        state = BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        state.repository_revision = new_rev
        state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    table = Table(title=f"detect-changes {old_rev[:8]}..{new_rev[:8]}")
    table.add_column("Kind")
    table.add_column("path::symbol")
    for path, symbol in changed_symbols:
        table.add_row("changed (needs_revalidation)", f"{path}::{symbol}")
    for path, symbol in new_symbols:
        table.add_row("new", f"{path}::{symbol}")
    console.print(table)
    console.print(
        f"[green]{len(changed_symbols)} changed, {len(new_symbols)} new symbol(s).[/green] "
        "Run `graph-cli impact <codeunit-id>` on changed ones."
    )
