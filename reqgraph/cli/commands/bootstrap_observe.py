"""`bootstrap-observe` — spec §7 B1. Heuristic but mechanical: derives
ObservedBehavior from each scanned Test's assert statements (`test` evidence)
and each CodeUnit's docstring/JSDoc (`documentation` evidence). No LLM call —
this is "principalmente deterministico" evidence extraction, not inference.

`--legacy` adds a third, lowest-confidence pass: for CodeUnits still
uncovered after the two passes above (no test, no doc comment — the common
case for an undocumented legacy codebase), it records the symbol's own
source body as `static-code` evidence. Without this, a project with neither
tests nor docstrings produces zero ObservedBehavior and `bootstrap-infer` has
nothing to reverse-engineer from.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Annotated, Callable

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.extract.registry import extract_docstring_for_symbol, extract_source_for_symbol
from reqgraph.graph.models import ObservedBehavior
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import codeunits, observed_behaviors, tests
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState


def _find_asserts(source: str, symbol: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    parts = symbol.split(".")
    func_name = parts[-1]
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target = node
            break
    if target is None:
        return []
    return [ast.unparse(n.test) for n in ast.walk(target) if isinstance(n, ast.Assert)]


def run(
    repo_path: Path = Path("."),
    legacy: Annotated[
        bool,
        typer.Option(
            "--legacy",
            help=(
                "Also derive low-confidence 'static-code' evidence, straight from a "
                "symbol's source, for CodeUnits with no test or doc-comment evidence. "
                "Use for projects with no test suite, where the two passes above "
                "would otherwise leave bootstrap-infer with nothing to work from."
            ),
        ),
    ] = False,
) -> None:
    run_impl(repo_path, legacy=legacy)


def run_impl(
    repo_path: Path = Path("."),
    legacy: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """See bootstrap_scan.run_impl's docstring for why this split exists."""
    root = project_root()
    progress = on_progress or (lambda _msg: None)
    created = 0
    with graph_session() as sess:
        all_tests = tests.list_all(sess)
        progress(f"{len(all_tests)} Test node(s) to check for assertion evidence.")
        for test_node in all_tests:
            if edges.outgoing_ids(sess, test_node.id, "EVIDENCES"):
                continue
            try:
                source = (repo_path / test_node.path).read_text(encoding="utf-8")
            except OSError:
                continue
            asserts = _find_asserts(source, test_node.symbol or "")
            if not asserts:
                continue
            progress(f"Evidence from test: {test_node.symbol} ({test_node.path})")
            confidence = "high" if len(asserts) == 1 else "medium"
            observed = ObservedBehavior(
                given=f"test {test_node.symbol} set up as coded in {test_node.path}",
                when=f"{test_node.symbol} runs",
                observed="; ".join(asserts),
                evidence_type="test",
                confidence=confidence,
                created_by="static-analysis",
            )
            observed_behaviors.create(sess, observed)
            edges.evidences(sess, test_node.id, observed.id)
            created += 1

        all_codeunits = codeunits.list_all(sess)
        progress(f"{len(all_codeunits)} CodeUnit node(s) to check for docstring evidence.")
        for codeunit_node in all_codeunits:
            if codeunit_node.kind not in ("function", "method"):
                continue
            if edges.outgoing_ids(sess, codeunit_node.id, "EVIDENCES"):
                continue
            try:
                source = (repo_path / codeunit_node.path).read_text(encoding="utf-8")
            except OSError:
                continue
            docstring = extract_docstring_for_symbol(codeunit_node.path, source, codeunit_node.symbol)
            if not docstring:
                continue
            progress(f"Evidence from docstring: {codeunit_node.symbol} ({codeunit_node.path})")
            observed = ObservedBehavior(
                given=f"{codeunit_node.symbol} as documented in {codeunit_node.path}",
                when=f"{codeunit_node.symbol} is called",
                observed=docstring,
                evidence_type="documentation",
                confidence="medium",
                created_by="static-analysis",
            )
            observed_behaviors.create(sess, observed)
            edges.evidences(sess, codeunit_node.id, observed.id)
            created += 1

        if legacy:
            progress("Legacy pass: raw source for CodeUnits still without any evidence.")
            for codeunit_node in all_codeunits:
                if codeunit_node.kind not in ("function", "method"):
                    continue
                if edges.outgoing_ids(sess, codeunit_node.id, "EVIDENCES"):
                    continue
                try:
                    source = (repo_path / codeunit_node.path).read_text(encoding="utf-8")
                except OSError:
                    continue
                body = extract_source_for_symbol(codeunit_node.path, source, codeunit_node.symbol)
                if not body:
                    continue
                progress(f"Evidence from source: {codeunit_node.symbol} ({codeunit_node.path})")
                observed = ObservedBehavior(
                    given=f"{codeunit_node.symbol} as implemented in {codeunit_node.path}",
                    when=f"{codeunit_node.symbol} is called",
                    observed=body,
                    evidence_type="static-code",
                    confidence="low",
                    created_by="static-analysis",
                )
                observed_behaviors.create(sess, observed)
                edges.evidences(sess, codeunit_node.id, observed.id)
                created += 1

    bootstrap_path = bootstrap_state_path(root)
    state = (
        BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        if bootstrap_path.exists()
        else BootstrapState()
    )
    state.stage = "observe"
    state.counts.observed_behaviors += created
    state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    summary = f"bootstrap-observe complete: {created} ObservedBehavior created."
    console.print(f"[green]{summary}[/green]")
    progress(summary)
