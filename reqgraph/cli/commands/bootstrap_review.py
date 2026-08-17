"""`bootstrap-review` — spec §7 B4. Walks the bootstrap review_queue; for
each candidate node the human picks one of the outcomes listed in the spec.
"correct" shares the same underlying primitive as the standalone `validate`
command.
"""

from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.models import Clarification, Issue
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import clarifications, issues
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState

DECISIONS = ("correct", "reword", "bug", "ambiguous", "obsolete", "insufficient")


def run(
    node_id: Annotated[str | None, typer.Option(help="Node id to review; default: next in review_queue")] = None,
    decision: Annotated[str, typer.Option(help=f"one of {DECISIONS}")] = "correct",
    note: Annotated[str, typer.Option(help="free-text note, e.g. reworded text or bug summary")] = "",
    by: Annotated[str, typer.Option(help="human:<id> making the decision")] = "human",
) -> None:
    if decision not in DECISIONS:
        raise typer.BadParameter(f"decision must be one of {DECISIONS}")

    root = project_root()
    bootstrap_path = bootstrap_state_path(root)
    state = (
        BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        if bootstrap_path.exists()
        else BootstrapState()
    )

    target_id = node_id
    if target_id is None:
        if not state.review_queue:
            console.print("[yellow]Review queue is empty.[/yellow]")
            raise typer.Exit(code=0)
        target_id = state.review_queue[0]

    with graph_session() as sess:
        record = sess.run("MATCH (n {id: $id}) RETURN labels(n)[0] AS label", id=target_id).single()
        if record is None:
            raise typer.BadParameter(f"no node with id={target_id!r}")
        label = record["label"]

        if decision in ("correct", "reword"):
            sess.run(
                f"MATCH (n:{label} {{id: $id}}) SET n.knowledge_status = 'validated', "
                "n.trust = 'human-validated', n.updated_at = datetime()",
                id=target_id,
            )
            if decision == "reword" and note:
                sess.run(
                    f"MATCH (n:{label} {{id: $id}}) SET n.source_refs = n.source_refs + $note",
                    id=target_id,
                    note=f"reword-note:{note}",
                )
            if label == "Contract":
                sess.run(
                    "MATCH (c:Contract {id: $id})-[f:FORMALIZES]->(:Requirement) SET f.reviewed_by = $by",
                    id=target_id,
                    by=by,
                )
        elif decision == "bug":
            issue = Issue(
                title=f"Possible bug surfaced during bootstrap review of {label} {target_id}",
                description=note or "(no note provided)",
                reported_by=by,
                classification="suspected_bug",
            )
            issues.create(sess, issue)
            if label in ("CodeUnit", "ConfigUnit"):
                edges.affects(sess, issue.id, target_id)
            console.print(f"  opened Issue {issue.id}")
        elif decision == "ambiguous":
            clar = Clarification(question=note or f"Is the inferred {label} {target_id} correct?", created_by=by)
            clarifications.create(sess, clar)
            if label == "Requirement":
                edges.clarifies(sess, clar.id, target_id)
            console.print(f"  opened Clarification {clar.id}")
        else:  # obsolete | insufficient
            sess.run(
                f"MATCH (n:{label} {{id: $id}}) SET n.source_refs = n.source_refs + $note, n.updated_at = datetime()",
                id=target_id,
                note=f"{decision}:{note or by}",
            )

    if target_id in state.review_queue:
        state.review_queue.remove(target_id)
    if decision in ("correct", "reword"):
        if label == "Requirement":
            state.counts.validated_requirements += 1
        elif label == "Contract":
            state.counts.validated_contracts += 1
    if not state.review_queue:
        state.stage = "complete"
    state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    console.print(f"[green]{label} {target_id}: {decision}[/green] (queue: {len(state.review_queue)} remaining)")
