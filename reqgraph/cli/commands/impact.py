"""`impact <codeunit|configunit>` — deterministic candidate traversal (spec
§9.2 step 4/6, models-config `impact_traversal_rules`) plus an optional
vector-similarity pass, then impact_analyst classification. Never sets
Contract.knowledge_status; writes an audit record under /.project-state/impact/
(an operational extension, not a new node label — see plan Ambiguity 7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.context.impact_context import gather
from reqgraph.extract.python_ast import extract_symbol_docstring
from reqgraph.graph.models import CodeUnit, ConfigUnit, Issue
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import codeunits, configunits, issues
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import impact_analyst
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import ImpactAnalystOutput
from reqgraph.state import io as state_io
from reqgraph.state.paths import impact_dir


def run(
    target_id: str,
    depth: Annotated[int, typer.Option(help="DEPENDS_ON traversal depth")] = 2,
    diff_text: Annotated[str, typer.Option(help="Diff/description of what changed, for the analyst")] = "",
    open_issue: Annotated[bool, typer.Option("--open-issue", help="Open an Issue if the analyst recommends it")] = False,
    repo_path: Annotated[
        Path | None,
        typer.Option(help="If given, enriches the vector-search query with the target's live docstring"),
    ] = None,
) -> None:
    root = project_root()
    with graph_session() as sess:
        record = sess.run("MATCH (n {id: $id}) RETURN labels(n)[0] AS label", id=target_id).single()
        if record is None:
            raise typer.BadParameter(f"no node with id={target_id!r}")
        label = record["label"]
        if label not in ("CodeUnit", "ConfigUnit"):
            raise typer.BadParameter(f"{label} is not impact-analyzable (must be CodeUnit or ConfigUnit)")

        repo = codeunits if label == "CodeUnit" else configunits
        target_node = repo.get(sess, target_id)
        embedding_query_text = _embedding_query_text(target_node, repo_path)

        candidates = gather(sess, target_id, label, depth=depth, embedding_query_text=embedding_query_text)
        if not candidates.contracts and not candidates.vector_candidate_contracts:
            console.print(f"[yellow]{label} {target_id} implements/constrains no Contract — nothing to assess.[/yellow]")
            raise typer.Exit(code=0)

        # _vector_candidate_contracts already excludes ids present in the deterministic set,
        # so the two lists below are disjoint by construction.
        contract_lines = [f"{c.id}: pre={c.preconditions} post={c.postconditions}" for c in candidates.contracts] + [
            f"{c.id}: pre={c.preconditions} post={c.postconditions} "
            "[vector-discovered candidate, not from deterministic traversal]"
            for c in candidates.vector_candidate_contracts
        ]
        output: ImpactAnalystOutput = invoke_role(
            ROLES["impact_analyst"],
            impact_analyst.system_prompt(),
            impact_analyst.user_prompt(target_id, diff_text or "(no diff text provided)", contract_lines),
            ImpactAnalystOutput,
        )

        if target_node is not None:
            repo.update_fields(sess, target_id, verification_status="needs_revalidation")

        opened_issue_id = None
        if open_issue and output.open_issue_recommended:
            issue = Issue(
                title=f"Impact analyst flagged risk on {label} {target_id}",
                description=output.issue_summary or "",
                reported_by=f"llm:{ROLES['impact_analyst'].default_model}",
                classification="regression",
            )
            issues.create(sess, issue)
            edges.affects(sess, issue.id, target_id)
            for impact in output.contract_impacts:
                if impact.risk in ("medium", "high"):
                    edges.violates(sess, issue.id, impact.contract_id)
            opened_issue_id = issue.id

    audit = {
        "target_id": target_id,
        "target_label": label,
        "at": datetime.now(UTC).isoformat(),
        "candidate_contracts": [c.id for c in candidates.contracts],
        "vector_candidate_contracts": [c.id for c in candidates.vector_candidate_contracts],
        "candidate_tests": [t.id for t in candidates.tests],
        "dependent_ids": candidates.dependent_ids,
        "open_issues": [i.id for i in candidates.open_issues],
        "analysis": output.model_dump(mode="json"),
        "opened_issue_id": opened_issue_id,
    }
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    state_io.write_json(impact_dir(root) / f"impact-{ts}.json", audit)

    console.print(f"[bold]Overall risk: {output.overall_risk}[/bold]")
    if candidates.vector_candidate_contracts:
        console.print(
            f"[dim]{len(candidates.vector_candidate_contracts)} additional candidate(s) found via vector search.[/dim]"
        )
    table = Table(title="Per-contract impact")
    table.add_column("Contract")
    table.add_column("Risk")
    table.add_column("Recommended action")
    for impact in output.contract_impacts:
        table.add_row(impact.contract_id, impact.risk, impact.recommended_action)
    console.print(table)
    if opened_issue_id:
        console.print(f"Opened Issue {opened_issue_id}")


def _embedding_query_text(target_node: CodeUnit | ConfigUnit | None, repo_path: Path | None) -> str | None:
    if isinstance(target_node, CodeUnit):
        text = f"{target_node.path} {target_node.symbol}"
        if repo_path is not None:
            try:
                source = (repo_path / target_node.path).read_text(encoding="utf-8")
                docstring = extract_symbol_docstring(target_node.path, source, target_node.symbol)
                if docstring:
                    text += f" {docstring}"
            except OSError:
                pass
        return text
    if isinstance(target_node, ConfigUnit):
        return f"{target_node.path} {target_node.key}"
    return None
