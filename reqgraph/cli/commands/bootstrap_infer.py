"""`bootstrap-infer` — spec §7 B2/B3. Groups ObservedBehavior evidence and
proposes ONE candidate Requirement/Contract/Example set per invocation
(`knowledge_status=inferred`). Run it again with a different `--observed-id`
selection for another behavioral cluster. Never marks anything validated —
enforced here, not just in the prompt (reverse_analyst hard_rule).
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.models import (
    AcceptanceCriterion,
    BehavioralSignature,
    Contract,
    Example,
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


def run(
    observed_id: Annotated[
        list[str] | None, typer.Option(help="ObservedBehavior id(s), repeatable. Default: all ungrouped.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Max ungrouped ObservedBehaviors to pull if --observed-id not given")] = 20,
) -> None:
    observed_id = observed_id or []
    root = project_root()
    with graph_session() as sess:
        if observed_id:
            behaviors = [b for b in (observed_behaviors.get(sess, oid) for oid in observed_id) if b]
        else:
            all_obs = observed_behaviors.list_all(sess)
            behaviors = [
                b for b in all_obs if not edges.incoming_ids(sess, b.id, "INFERRED_FROM")
            ][:limit]

        if not behaviors:
            console.print("[yellow]No ObservedBehavior available to infer from.[/yellow]")
            raise typer.Exit(code=0)

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

    bootstrap_path = bootstrap_state_path(root)
    state = (
        BootstrapState.model_validate(state_io.read_json(bootstrap_path))
        if bootstrap_path.exists()
        else BootstrapState()
    )
    state.stage = "infer"
    state.counts.candidate_requirements += 1
    state.counts.candidate_contracts += 1
    state.review_queue.extend([requirement.id, contract.id, *example_ids])
    state_io.write_json(bootstrap_path, state.model_dump(mode="json"))

    console.print(f"[green]Inferred candidate[/green] Requirement {requirement.id} / Contract {contract.id}")
    console.print(f"  rationale: {output.rationale}")
    table = Table(title="Candidate Examples")
    table.add_column("id")
    table.add_column("edge_case")
    for eid, e in zip(example_ids, output.examples):
        table.add_row(eid, str(e.edge_case))
    console.print(table)
    console.print("Next: `graph-cli bootstrap-review --next` to walk the review queue.")
