from __future__ import annotations

import typer
from rich.table import Table

from reqgraph.cli.common import console, graph_session
from reqgraph.graph.models import Assumption, Clarification
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import assumptions, clarifications, requirements
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import critic
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import CriticOutput


def run(requirement_id: str) -> None:
    with graph_session() as sess:
        requirement = requirements.get(sess, requirement_id)
        if requirement is None:
            raise typer.BadParameter(f"no Requirement with id={requirement_id!r}")

        existing = [
            c.question
            for c in (clarifications.get(sess, cid) for cid in edges.incoming_ids(sess, requirement_id, "CLARIFIES"))
            if c
        ]

        output: CriticOutput = invoke_role(
            ROLES["critic"],
            critic.system_prompt(),
            critic.user_prompt(requirement.text, existing),
            CriticOutput,
        )

        for clarification_draft in output.clarifications:
            clarification = Clarification(
                question=clarification_draft.question,
                blocking=clarification_draft.blocking,
                created_by="llm:critic",
            )
            clarifications.create(sess, clarification)
            edges.clarifies(sess, clarification.id, requirement_id)
        for assumption_draft in output.assumptions:
            assumption = Assumption(
                text=assumption_draft.text, rationale=assumption_draft.rationale, created_by="llm:critic"
            )
            assumptions.create(sess, assumption)
            edges.clarifies(sess, assumption.id, requirement_id)
        for contradiction_draft in output.contradictions:
            edges.contradicts(
                sess,
                requirement_id,
                contradiction_draft.other_requirement_id,
                status="open",
                resolution=contradiction_draft.summary,
            )

    console.print(f"[bold]Critic summary:[/bold] {output.summary}")
    table = Table(title="New Clarifications/Assumptions")
    table.add_column("Kind")
    table.add_column("Text")
    table.add_column("Blocking")
    for c in output.clarifications:
        table.add_row("Clarification", c.question, "yes" if c.blocking else "no")
    for a in output.assumptions:
        table.add_row("Assumption", a.text, "-")
    console.print(table)
    if any(c.blocking for c in output.clarifications):
        console.print(
            "[yellow]Blocking clarifications exist — resolve them before `formalize` "
            "(or pass --force to override).[/yellow]"
        )
