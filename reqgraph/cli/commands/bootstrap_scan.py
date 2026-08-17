"""`bootstrap-scan <repo-path>` — deterministic repository scan (spec §7 B0).
Python-only via `extract/python_ast.py`. Never creates Requirement/Contract —
only observed CodeUnit/ConfigUnit/Test and module-level DEPENDS_ON.
"""

from __future__ import annotations

from pathlib import Path

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.extract.config_extractor import extract_config_units, is_config_path
from reqgraph.extract.git_diff import GitError, current_revision, list_tracked_files
from reqgraph.extract.hashing import sha256_text
from reqgraph.extract.python_ast import PythonExtractor, module_name_for
from reqgraph.graph.models import CodeUnit, ConfigUnit, Test
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import codeunits, configunits, tests
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState


def run(repo_path: Path) -> None:
    root = project_root()
    extractor = PythonExtractor()

    py_files = list_tracked_files(repo_path, suffix=".py")
    all_files = _list_all_tracked(repo_path)
    module_by_file: dict[str, str] = {p: module_name_for(p) for p in py_files}

    codeunit_count = 0
    test_count = 0
    configunit_count = 0

    with graph_session() as sess:
        module_node_ids: dict[str, str] = {}
        file_imports: dict[str, list[str]] = {}

        for path in py_files:
            source = (repo_path / path).read_text(encoding="utf-8")
            module_name = module_by_file[path]

            module_node = CodeUnit(
                path=path, symbol=module_name, kind="module", hash=sha256_text(source), created_by="static-analysis"
            )
            existing_module = codeunits.find_current(sess, path, module_name)
            if existing_module is None or existing_module.hash != module_node.hash:
                codeunits.create(sess, module_node)
                module_node_ids[path] = module_node.id
                codeunit_count += 1
            else:
                module_node_ids[path] = existing_module.id

            result = extractor.extract(path, source)
            file_imports[path] = [imp.imports for imp in result.imports]

            for symbol_unit in result.codeunits:
                existing = codeunits.find_current(sess, symbol_unit.path, symbol_unit.symbol)
                if existing is not None and existing.hash == symbol_unit.hash:
                    continue
                node = CodeUnit(
                    path=symbol_unit.path,
                    symbol=symbol_unit.symbol,
                    kind=symbol_unit.kind,
                    hash=symbol_unit.hash,
                    created_by="static-analysis",
                )
                if existing is not None:
                    codeunits.create_version(sess, node, existing.id, carry_forward_implements=False)
                else:
                    codeunits.create(sess, node)
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

        # module-level DEPENDS_ON, intra-repo only
        for path, imports in file_imports.items():
            for imp in imports:
                for other_path, other_module in module_by_file.items():
                    if other_path == path:
                        continue
                    if imp == other_module or imp.startswith(other_module + "."):
                        edges.depends_on(sess, module_node_ids[path], module_node_ids[other_path], kind="import")

        for path in all_files:
            if path in module_by_file or not is_config_path(path):
                continue
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

    console.print(
        f"[green]bootstrap-scan complete:[/green] {codeunit_count} CodeUnit, "
        f"{test_count} Test, {configunit_count} ConfigUnit written/updated."
    )


def _list_all_tracked(repo_path: Path) -> list[str]:
    try:
        return list_tracked_files(repo_path, suffix="")
    except GitError:
        return []


def _safe_revision(repo_path: Path) -> str:
    try:
        return current_revision(repo_path)
    except GitError:
        return ""
