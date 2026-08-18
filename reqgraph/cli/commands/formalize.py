from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from reqgraph.cli.common import console, graph_session
from reqgraph.graph.models import AcceptanceCriterion, BehavioralSignature, Contract, Example
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import clarifications, contracts, examples, requirements
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import formalizer
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import FormalizerOutput


def _gate_check(output: FormalizerOutput) -> str | None:
    if len(output.examples) < 3:
        return f"need >=3 Examples, got {len(output.examples)}"
    if not any(e.edge_case for e in output.examples):
        return "need >=1 Example with edge_case=true, none found"
    return None


def run(
    requirement_id: Annotated[str, typer.Option(help="Requirement id to formalize")],
    force: Annotated[bool, typer.Option("--force", help="Bypass unresolved blocking-clarification gate")] = False,
) -> None:
    with graph_session() as sess:
        requirement = requirements.get(sess, requirement_id)
        if requirement is None:
            raise typer.BadParameter(f"no Requirement with id={requirement_id!r}")

        clarification_ids = edges.incoming_ids(sess, requirement_id, "CLARIFIES")
        all_clarifications = [c for c in (clarifications.get(sess, cid) for cid in clarification_ids) if c]
        unresolved_blocking = [c for c in all_clarifications if c.blocking and c.answer is None]
        if unresolved_blocking and not force:
            console.print(
                f"[red]Refusing to formalize: {len(unresolved_blocking)} unresolved blocking "
                "Clarification(s) exist (spec §6 G0 gate). Resolve them, or pass --force.[/red]"
            )
            for c in unresolved_blocking:
                console.print(f"  - {c.question}")
            raise typer.Exit(code=1)

        resolved = [(c.question, c.answer) for c in all_clarifications if c.answer is not None]

        output: FormalizerOutput = invoke_role(
            ROLES["formalizer"],
            formalizer.system_prompt(),
            formalizer.user_prompt(requirement.text, resolved),
            FormalizerOutput,
            validate=_gate_check,
        )

        contract = Contract(
            summary=output.contract.summary,
            preconditions=output.contract.preconditions,
            postconditions=output.contract.postconditions,
            invariants=output.contract.invariants,
            acceptance=[
                AcceptanceCriterion(given=a.given, when=a.when, then=a.then) for a in output.contract.acceptance
            ],
            origin_mode="greenfield",
            knowledge_status="generated",
            created_by=f"llm:{ROLES['formalizer'].default_model}",
        )
        contracts.create(sess, contract)
        edges.formalizes(sess, contract.id, requirement_id, generated_by=f"llm:{ROLES['formalizer'].default_model}")

        example_ids = []
        for e in output.examples:
            example = Example(
                summary=e.summary,
                input=e.input,
                expected_output=e.expected_output,
                edge_case=e.edge_case,
                behavioral_signature=BehavioralSignature(**e.behavioral_signature.model_dump()),
                origin="formalizer",
                knowledge_status="generated",
                created_by=f"llm:{ROLES['formalizer'].default_model}",
            )
            examples.create(sess, example)
            edges.witnesses(sess, example.id, contract.id)
            example_ids.append(example.id)

    console.print(f"[green]Formalized Contract[/green] {contract.id} <- Requirement {requirement_id}")
    table = Table(title=f"{len(output.examples)} Examples")
    table.add_column("id")
    table.add_column("edge_case")
    table.add_column("input")
    table.add_column("expected_output")
    for eid, e in zip(example_ids, output.examples):
        table.add_row(eid, str(e.edge_case), str(e.input), str(e.expected_output))
    console.print(table)
    console.print(f"Next: `graph-cli validate {contract.id}` and each Example, then `derive-tasks`.")
