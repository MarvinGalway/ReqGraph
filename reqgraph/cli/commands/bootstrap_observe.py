"""`bootstrap-observe` — spec §7 B1. Heuristic but mechanical: derives
ObservedBehavior from each scanned Test's assert statements. No LLM call —
this is "principalmente deterministico" evidence extraction, not inference.
"""

from __future__ import annotations

import ast
from pathlib import Path

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.models import ObservedBehavior
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import observed_behaviors, tests
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


def run(repo_path: Path = Path(".")) -> None:
    root = project_root()
    created = 0
    with graph_session() as sess:
        all_tests = tests.list_all(sess)
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

    bootstrap_path = bootstrap_state_path(root)
    state = (
        BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        if bootstrap_path.exists()
        else BootstrapState()
    )
    state.stage = "observe"
    state.counts.observed_behaviors += created
    state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    console.print(f"[green]bootstrap-observe complete:[/green] {created} ObservedBehavior created.")
