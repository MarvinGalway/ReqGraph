"""`bootstrap-scan <repo-path>` — deterministic repository scan (spec §7 B0).
Language-agnostic at this layer: file discovery finds every path any
registered `Extractor` (see `extract/registry.py`) claims, currently Python
always and JavaScript/TypeScript when the `js` extra is installed. Never
creates Requirement/Contract — only observed CodeUnit/ConfigUnit/Test,
module-level + intra-file-call DEPENDS_ON, and (optional, git-repo-only)
commit-history provenance on each module CodeUnit's `source_refs`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Callable

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.extract.base import ExtractedCall, Extractor
from reqgraph.extract.config_extractor import extract_config_units, is_config_path
from reqgraph.extract.git_diff import (
    GitError,
    current_revision,
    file_commit_history,
    list_tracked_files,
)
from reqgraph.extract.hashing import sha256_text
from reqgraph.extract.naming import path_to_module_name
from reqgraph.extract.registry import get_extractor_for
from reqgraph.graph.models import CodeUnit, ConfigUnit, Test
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import codeunits, configunits, tests
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState


def run(
    repo_path: Path,
    include_lockfiles: Annotated[
        bool,
        typer.Option(
            help="Also extract ConfigUnit from dependency lockfiles (package-lock.json, "
            "yarn.lock, ...). Off by default: a lockfile isn't project configuration and "
            "produces hundreds of noise ConfigUnit per file."
        ),
    ] = False,
) -> None:
    run_impl(repo_path, include_lockfiles=include_lockfiles)


def run_impl(
    repo_path: Path,
    include_lockfiles: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """The actual scan, minus Typer's CLI-parameter wrapping — `run()` above
    is what `graph-cli bootstrap-scan` registers (Typer/Click can't build a
    CLI option for a `Callable` parameter, so `on_progress` can't live on a
    function registered directly as a command). Callers that want live
    progress (the API server) call this directly instead of `run()`.
    """
    root = project_root()
    progress = on_progress or (lambda _msg: None)

    all_files = _list_all_tracked(repo_path)
    code_files: dict[str, Extractor] = {
        p: extractor for p in all_files if (extractor := get_extractor_for(p)) is not None
    }
    module_by_file: dict[str, str] = {p: path_to_module_name(p) for p in code_files}
    progress(f"Found {len(all_files)} tracked file(s), {len(code_files)} recognized as code.")

    codeunit_count = 0
    test_count = 0
    configunit_count = 0
    call_edge_count = 0

    with graph_session() as sess:
        # (path, symbol) -> current graph id, populated as symbols are seen —
        # backs both the import graph (module-level) and the call graph.
        symbol_ids: dict[tuple[str, str], str] = {}
        file_imports: dict[str, list[str]] = {}
        file_calls: dict[str, list[ExtractedCall]] = {}

        for path, extractor in code_files.items():
            progress(f"Scanning {path}")
            source = (repo_path / path).read_text(encoding="utf-8")
            module_name = module_by_file[path]
            file_hash = sha256_text(source)

            existing_module = codeunits.find_current(sess, path, module_name)
            if existing_module is None or existing_module.hash != file_hash:
                history = file_commit_history(repo_path, path)
                source_refs = [
                    f"git:{c.commit_hash[:8]} {c.author} {c.date} {c.subject}" for c in history
                ]
                module_node = CodeUnit(
                    path=path,
                    symbol=module_name,
                    kind="module",
                    hash=file_hash,
                    created_by="static-analysis",
                    source_refs=source_refs,
                    language=extractor.language,
                )
                codeunits.create(sess, module_node)
                symbol_ids[(path, module_name)] = module_node.id
                codeunit_count += 1
            else:
                symbol_ids[(path, module_name)] = existing_module.id

            result = extractor.extract(path, source)
            file_imports[path] = [imp.imports for imp in result.imports]
            file_calls[path] = result.calls

            for symbol_unit in result.codeunits:
                existing = codeunits.find_current(sess, symbol_unit.path, symbol_unit.symbol)
                if existing is not None and existing.hash == symbol_unit.hash:
                    symbol_ids[(path, symbol_unit.symbol)] = existing.id
                    continue
                node = CodeUnit(
                    path=symbol_unit.path,
                    symbol=symbol_unit.symbol,
                    kind=symbol_unit.kind,
                    hash=symbol_unit.hash,
                    created_by="static-analysis",
                    language=symbol_unit.language,
                )
                if existing is not None:
                    codeunits.create_version(sess, node, existing.id, carry_forward_implements=False)
                else:
                    codeunits.create(sess, node)
                symbol_ids[(path, symbol_unit.symbol)] = node.id
                codeunit_count += 1

            for test_unit in result.tests:
                existing_test = tests.find_by_path_symbol(sess, test_unit.path, test_unit.symbol)
                if existing_test is not None:
                    continue
                test_node = Test(
                    path=test_unit.path,
                    symbol=test_unit.symbol,
                    framework=test_unit.framework,
                    created_by="static-analysis",
                )
                tests.create(sess, test_node)
                test_count += 1

        # module-level DEPENDS_ON (import), intra-repo only
        for path, imports in file_imports.items():
            for imp in imports:
                for other_path, other_module in module_by_file.items():
                    if other_path == path:
                        continue
                    if imp == other_module or imp.startswith(other_module + "."):
                        edges.depends_on(
                            sess, symbol_ids[(path, module_by_file[path])], symbol_ids[(other_path, other_module)], kind="import"
                        )

        # symbol-level DEPENDS_ON (call), intra-file only — see extract/python_ast.py, extract/javascript_ts.py
        for path, calls in file_calls.items():
            seen_pairs: set[tuple[str, str]] = set()
            for call in calls:
                caller_id = symbol_ids.get((path, call.caller_symbol))
                callee_id = symbol_ids.get((path, call.callee_symbol))
                if caller_id is None or callee_id is None or (caller_id, callee_id) in seen_pairs:
                    continue
                seen_pairs.add((caller_id, callee_id))
                edges.depends_on(sess, caller_id, callee_id, kind="call")
                call_edge_count += 1

        for path in all_files:
            if path in code_files or not is_config_path(path, include_lockfiles=include_lockfiles):
                continue
            progress(f"Extracting config from {path}")
            source = (repo_path / path).read_text(encoding="utf-8")
            for cfg in extract_config_units(path, source):
                existing_cfg = configunits.find_current(sess, cfg.path, cfg.key)
                if existing_cfg is not None and existing_cfg.value_hash == cfg.value_hash:
                    continue
                config_node = ConfigUnit(
                    path=cfg.path,
                    key=cfg.key,
                    kind=cfg.kind,
                    value_hash=cfg.value_hash,
                    scope_hint=cfg.scope_hint,
                    created_by="static-analysis",
                )
                if existing_cfg is not None:
                    configunits.create_version(sess, config_node, existing_cfg.id, carry_forward_constrains=False)
                else:
                    configunits.create(sess, config_node)
                configunit_count += 1

    bootstrap_path = bootstrap_state_path(root)
    state = (
        BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        if bootstrap_path.exists()
        else BootstrapState()
    )
    state.stage = "scan"
    state.repository_revision = _safe_revision(repo_path)
    state.counts.codeunits += codeunit_count
    state.counts.configunits += configunit_count
    state.counts.tests += test_count
    state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    summary = (
        f"bootstrap-scan complete: {codeunit_count} CodeUnit, {test_count} Test, "
        f"{configunit_count} ConfigUnit written/updated, {call_edge_count} call-graph edge(s)."
    )
    console.print(f"[green]{summary}[/green]")
    progress(summary)


_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build"}


def _walk_files(repo_path: Path, suffix: str) -> list[str]:
    """Non-git fallback file discovery — used when `repo_path` isn't a git
    repo (git ls-files requires one). No .gitignore awareness, just a
    reasonable default exclude list.
    """
    results = []
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_path)
        if any(part in _EXCLUDED_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        rel_str = str(rel)
        if not suffix or rel_str.endswith(suffix):
            results.append(rel_str)
    return results


def _list_all_tracked(repo_path: Path) -> list[str]:
    try:
        return list_tracked_files(repo_path, suffix="")
    except GitError:
        return _walk_files(repo_path, "")


def _safe_revision(repo_path: Path) -> str:
    try:
        return current_revision(repo_path)
    except GitError:
        return ""
