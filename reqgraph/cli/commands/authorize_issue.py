from __future__ import annotations

from typing import Annotated

import typer

from reqgraph.cli.common import console, graph_session, project_root
from reqgraph.graph.repositories.registry import issues
from reqgraph.state import io as state_io
from reqgraph.state.paths import issue_file_path

DECISION_TO_WORKFLOW = {
    "resolve": "ready",
    "backlog": "open",
    "reject": "rejected",
    "expected_behavior": "closed",
}


def run(
    issue_id: str,
    decision: Annotated[str, typer.Option(help="resolve | backlog | reject | expected_behavior")],
) -> None:
    if decision not in DECISION_TO_WORKFLOW:
        raise typer.BadParameter(f"decision must be one of {list(DECISION_TO_WORKFLOW)}")

    root = project_root()
    with graph_session() as sess:
        issue = issues.get(sess, issue_id)
        if issue is None:
            raise typer.BadParameter(f"no Issue with id={issue_id!r}")
        new_workflow_status = DECISION_TO_WORKFLOW[decision]
        fields: dict = {"workflow_status": new_workflow_status}
        if decision == "expected_behavior":
            fields["classification"] = "expected_behavior"
            fields["resolution"] = "expected_behavior"
        issues.update_fields(sess, issue_id, **fields)

    issue_path = issue_file_path(root, issue_id)
    if issue_path.exists():
        data = state_io.read_json(issue_path)
        data["human_decision"] = decision
        state_io.write_json(issue_path, data)

    console.print(f"Issue {issue_id}: human_decision={decision} -> workflow_status={new_workflow_status}")
    if decision == "resolve":
        console.print(
            "  Note: this does NOT create a Task. Run "
            f"`graph-cli derive-tasks --issue-id {issue_id}` once you've decided on a Contract."
        )
