"""`bootstrap-infer` — spec §7 B2/B3. Groups ObservedBehavior evidence
(deterministically, by the file path of the evidencing Test/CodeUnit — real
embeddings-based clustering was considered and deferred, same reasoning as
the graph-cli foundation pass's embeddings decision) and proposes one
candidate Requirement/Contract/Example set per group (`knowledge_status=
inferred`). Never marks anything validated — enforced here, not just in the
prompt (reverse_analyst hard_rule).
"""

from __future__ import annotations

from typing import Annotated, Callable

import typer
from neo4j import Session
from rich.table import Table

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.models import (
    AcceptanceCriterion,
    BehavioralSignature,
    Contract,
    Example,
    ObservedBehavior,
    Requirement,
)
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import (
    contracts,
    examples,
    observed_behaviors,
    requirements,
)
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import reverse_analyst
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import ReverseAnalystOutput
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState

MODEL = ROLES["reverse_analyst"].default_model


def _ungrouped_behaviors_by_path(sess: Session) -> dict[str, list[str]]:
    """Deterministic grouping: ObservedBehavior ids not yet INFERRED_FROM-
    referenced, bucketed by the file path of whatever evidences them
    (Test or CodeUnit — both carry `.path`).
    """
    result = sess.run(
        """
        MATCH (b:ObservedBehavior)
        WHERE NOT EXISTS { MATCH (b)<-[:INFERRED_FROM]-() }
        OPTIONAL MATCH (b)<-[:EVIDENCES]-(source)
        RETURN b.id AS id, coalesce(source.path, 'unknown') AS path
        """
    )
    groups: dict[str, list[str]] = {}
    for record in result:
        groups.setdefault(record["path"], []).append(record["id"])
    return groups


def _infer_one_group(
    sess: Session, behaviors: list[ObservedBehavior]
) -> tuple[Requirement, Contract, list[str], ReverseAnalystOutput]:
    descriptions = [f"[{b.id}] given {b.given}; when {b.when}; observed {b.observed}" for b in behaviors]
    output: ReverseAnalystOutput = invoke_role(
        ROLES["reverse_analyst"],
        reverse_analyst.system_prompt(),
        reverse_analyst.user_prompt(descriptions),
        ReverseAnalystOutput,
    )

    requirement = Requirement(
        text=output.requirement.text,
        source="reverse-engineered",
        trust="external-unverified",
        origin_mode="legacy-bootstrap",
        knowledge_status="inferred",
        created_by=f"llm:{MODEL}",
    )
    requirements.create(sess, requirement)

    contract = Contract(
        summary=output.contract.summary,
        preconditions=output.contract.preconditions,
        postconditions=output.contract.postconditions,
        invariants=output.contract.invariants,
        acceptance=[AcceptanceCriterion(**a.model_dump()) for a in output.contract.acceptance],
        origin_mode="legacy-bootstrap",
        knowledge_status="inferred",
        created_by=f"llm:{MODEL}",
    )
    contracts.create(sess, contract)
    edges.formalizes(sess, contract.id, requirement.id, knowledge_status="inferred", generated_by=f"llm:{MODEL}")

    example_ids = []
    for e in output.examples:
        example = Example(
            summary=e.summary,
            input=e.input,
            expected_output=e.expected_output,
            edge_case=e.edge_case,
            behavioral_signature=BehavioralSignature(**e.behavioral_signature.model_dump()),
            origin="inferred-from-existing-test",
            knowledge_status="inferred",
            created_by=f"llm:{MODEL}",
        )
        examples.create(sess, example)
        edges.witnesses(sess, example.id, contract.id)
        example_ids.append(example.id)

    for b in behaviors:
        edges.inferred_from(sess, requirement.id, b.id)
        edges.inferred_from(sess, contract.id, b.id)
        edges.supports(sess, b.id, contract.id)

    return requirement, contract, example_ids, output


def run(
    observed_id: Annotated[
        list[str] | None,
        typer.Option(help="ObservedBehavior id(s), repeatable. Bypasses grouping — treated as one explicit group."),
    ] = None,
    max_groups: Annotated[
        int, typer.Option(help="Max evidence groups to process this run (one LLM call per group)")
    ] = 10,
) -> None:
    run_impl(observed_id=observed_id, max_groups=max_groups)


def run_impl(
    observed_id: list[str] | None = None,
    max_groups: int = 10,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """See bootstrap_scan.run_impl's docstring for why this split exists."""
    observed_id = observed_id or []
    root = project_root()
    progress = on_progress or (lambda _msg: None)
    results: list[tuple[Requirement, Contract, list[str], ReverseAnalystOutput]] = []

    with graph_session() as sess:
        if observed_id:
            behaviors = [b for b in (observed_behaviors.get(sess, oid) for oid in observed_id) if b]
            if not behaviors:
                console.print("[yellow]None of the given --observed-id were found.[/yellow]")
                progress("No ObservedBehavior found for the given --observed-id.")
                raise typer.Exit(code=0)
            progress(f"Inferring from {len(behaviors)} explicitly given ObservedBehavior (1 LLM call)...")
            results.append(_infer_one_group(sess, behaviors))
        else:
            groups_by_path = _ungrouped_behaviors_by_path(sess)
            if not groups_by_path:
                console.print("[yellow]No ObservedBehavior available to infer from.[/yellow]")
                progress("No ObservedBehavior available to infer from — run bootstrap-observe first.")
                raise typer.Exit(code=0)
            paths = sorted(groups_by_path)[:max_groups]
            for i, path in enumerate(paths, start=1):
                behaviors = [b for b in (observed_behaviors.get(sess, oid) for oid in groups_by_path[path]) if b]
                if not behaviors:
                    continue
                console.print(f"[dim]Grouping {len(behaviors)} ObservedBehavior from {path!r}...[/dim]")
                progress(f"[{i}/{len(paths)}] Inferring Requirement/Contract from {len(behaviors)} evidence in {path!r} (LLM call)...")
                results.append(_infer_one_group(sess, behaviors))

    bootstrap_path = bootstrap_state_path(root)
    state = (
        BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        if bootstrap_path.exists()
        else BootstrapState()
    )
    state.stage = "infer"
    state.counts.candidate_requirements += len(results)
    state.counts.candidate_contracts += len(results)
    for requirement, contract, example_ids, _output in results:
        state.review_queue.extend([requirement.id, contract.id, *example_ids])
    state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    table = Table(title=f"{len(results)} candidate Requirement/Contract group(s) inferred")
    table.add_column("Requirement")
    table.add_column("Contract")
    table.add_column("Examples")
    table.add_column("Rationale")
    for requirement, contract, example_ids, output in results:
        table.add_row(requirement.id, contract.id, str(len(example_ids)), output.rationale)
    console.print(table)
    console.print("Next: `graph-cli bootstrap-review` to walk the review queue.")
    progress(f"bootstrap-infer complete: {len(results)} candidate Requirement/Contract group(s) inferred.")
