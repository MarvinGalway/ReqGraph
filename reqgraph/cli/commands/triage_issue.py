"""`triage-issue <issue-id>` — spec §8. Classification/candidate-linking
only; hard_rule: never authorizes modification. Candidates come from the
Issue's graph neighborhood (AFFECTS/VIOLATES/EXPLAINED_BY/FOUND_DURING) plus,
when the `embeddings` extra + vector indexes are available, similar
Contracts and similar Issues (the latter is a real duplicate-detection
capability the graph-neighborhood-only version couldn't offer) found via
vector search — purely additional context for the LLM, never authorization.
"""

from __future__ import annotations

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.registry import issues
from reqgraph.graph.vector_search import vector_search
from reqgraph.llm.embeddings import get_embedding_provider
from reqgraph.llm.invoke import invoke_role
from reqgraph.llm.prompts import issue_triage
from reqgraph.llm.roles import ROLES
from reqgraph.llm.schemas import IssueTriageOutput
from reqgraph.state import io as state_io
from reqgraph.state.paths import issue_file_path
from reqgraph.state.schemas import IssueFile


def run(issue_id: str) -> None:
    root = project_root()
    with graph_session() as sess:
        issue = issues.get(sess, issue_id)
        if issue is None:
            raise typer.BadParameter(f"no Issue with id={issue_id!r}")

        neighborhood_lines = []
        for edge_type in ("AFFECTS", "VIOLATES", "EXPLAINED_BY", "FOUND_DURING"):
            for target_id in edges.outgoing_ids(sess, issue_id, edge_type):
                neighborhood_lines.append(f"{edge_type} -> {target_id}")

        provider = get_embedding_provider()
        if provider is not None:
            query_vector = provider.embed(f"{issue.title} {issue.description}")
            for contract_id, score in vector_search(sess, "Contract", query_vector, k=3):
                neighborhood_lines.append(f"VECTOR_SIMILAR_CONTRACT -> {contract_id} (score={score:.3f})")
            for similar_id, score in vector_search(sess, "Issue", query_vector, k=3, exclude_id=issue_id):
                neighborhood_lines.append(f"VECTOR_SIMILAR_ISSUE -> {similar_id} (score={score:.3f})")

        output: IssueTriageOutput = invoke_role(
            ROLES["issue_triage"],
            issue_triage.system_prompt(),
            issue_triage.user_prompt(issue.title, issue.description, "\n".join(neighborhood_lines) or "(none linked yet)"),
            IssueTriageOutput,
        )

        issues.update_fields(
            sess, issue_id, workflow_status="triaging", classification=output.classification, severity=output.severity
        )
        for cid in output.candidate_contract_ids:
            edges.explained_by(sess, issue_id, cid)

    issue_path = issue_file_path(root, issue_id)
    data = (
        IssueFile.model_validate(state_io.read_json(issue_path))
        if issue_path.exists()
        else IssueFile(issue_id=issue_id)
    )
    data.candidate_contracts = output.candidate_contract_ids
    data.candidate_codeunits = output.candidate_codeunit_ids
    data.candidate_configunits = output.candidate_configunit_ids
    state_io.write_json(issue_path, data.model_dump(mode="json"))

    console.print(f"[bold]Triage:[/bold] classification={output.classification} severity={output.severity}")
    console.print(f"  rationale: {output.rationale}")
    console.print(
        "  This does NOT authorize modification — run `authorize-issue` for a human decision."
    )
