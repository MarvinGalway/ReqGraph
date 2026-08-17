from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from reqgraph.cli.main import app
from reqgraph.graph.driver import session as graph_session
from reqgraph.llm.schemas import ClarificationDraft, CriticOutput

pytestmark = pytest.mark.integration

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_init_status_consistency_check_happy_path(neo4j_session):
    result = runner.invoke(app, ["init", "--project", "Demo"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "Demo" in result.output

    result = runner.invoke(app, ["consistency-check", "--strict"])
    assert result.exit_code == 0, result.output


def test_ingest_requirements_then_run_critic_with_fake_llm(neo4j_session, fake_anthropic):
    runner.invoke(app, ["init", "--project", "Demo"])

    result = runner.invoke(
        app, ["ingest-requirements", "--text", "Users can cancel an order unless shipped."]
    )
    assert result.exit_code == 0, result.output
    match = re.search(r"Ingested Requirement ([0-9a-f-]+)", _strip_ansi(result.output))
    assert match is not None
    requirement_id = match.group(1)

    fake_anthropic(
        responses=[
            CriticOutput(
                clarifications=[ClarificationDraft(question="What counts as 'shipped'?", blocking=True)],
                summary="One blocking ambiguity found.",
            )
        ]
    )
    result = runner.invoke(app, ["run-critic", requirement_id])
    assert result.exit_code == 0, result.output
    assert "One blocking ambiguity found." in result.output

    with graph_session() as sess:
        record = sess.run(
            "MATCH (c:Clarification)-[:CLARIFIES]->(:Requirement {id: $id}) RETURN count(c) AS n",
            id=requirement_id,
        ).single()
        assert record["n"] == 1

    # formalize must refuse: the blocking clarification is unresolved
    result = runner.invoke(app, ["formalize", "--requirement-id", requirement_id])
    assert result.exit_code == 1
    assert "unresolved blocking" in _strip_ansi(result.output)
