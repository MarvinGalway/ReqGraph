from __future__ import annotations

import subprocess

import pytest
from typer.testing import CliRunner

from reqgraph.cli.main import app
from reqgraph.graph.repositories.codeunit import CodeUnitRepository
from reqgraph.graph.repositories.edges import outgoing_ids
from reqgraph.graph.repositories.observed_behavior import ObservedBehaviorRepository
from reqgraph.llm.schemas import (
    AcceptanceCriterionDraft,
    BehavioralSignatureDraft,
    CandidateRequirementDraft,
    ContractDraft,
    ExampleDraft,
    ReverseAnalystOutput,
)

pytestmark = pytest.mark.integration

runner = CliRunner()


def _git_init_and_commit(repo):
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial import"], cwd=repo, check=True, capture_output=True)


def test_bootstrap_scan_extracts_javascript_alongside_python(neo4j_session, project_root, target_repo_js):
    pytest.importorskip("tree_sitter_javascript")
    _git_init_and_commit(target_repo_js)

    result = runner.invoke(app, ["bootstrap-scan", str(target_repo_js)])
    assert result.exit_code == 0, result.output

    repo = CodeUnitRepository()
    cancel_order = repo.find_current(neo4j_session, "orders.js", "orders.cancelOrder")
    refund_order = repo.find_current(neo4j_session, "orders.js", "orders.refundOrder")
    mark_refunded = repo.find_current(neo4j_session, "orders.js", "orders.markRefunded")
    assert cancel_order is not None
    assert cancel_order.language == "javascript"
    assert refund_order is not None and mark_refunded is not None
    assert outgoing_ids(neo4j_session, refund_order.id, "DEPENDS_ON") == [mark_refunded.id]

    record = neo4j_session.run("MATCH (t:Test) WHERE t.path = 'orders.test.js' RETURN count(t) AS n").single()
    assert record["n"] == 2


def test_bootstrap_scan_creates_call_graph_and_git_provenance(neo4j_session, project_root, target_repo):
    _git_init_and_commit(target_repo)

    result = runner.invoke(app, ["bootstrap-scan", str(target_repo)])
    assert result.exit_code == 0, result.output
    assert "call-graph edge" in result.output

    repo = CodeUnitRepository()
    refund_order = repo.find_current(neo4j_session, "orders.py", "orders.refund_order")
    mark_refunded = repo.find_current(neo4j_session, "orders.py", "orders._mark_refunded")
    assert refund_order is not None and mark_refunded is not None
    assert outgoing_ids(neo4j_session, refund_order.id, "DEPENDS_ON") == [mark_refunded.id]

    module_node = repo.find_current(neo4j_session, "orders.py", "orders")
    assert module_node is not None
    assert any(ref.startswith("git:") for ref in module_node.source_refs)
    assert any("initial import" in ref for ref in module_node.source_refs)


def test_bootstrap_observe_creates_documentation_evidence(neo4j_session, project_root, target_repo):
    _git_init_and_commit(target_repo)
    runner.invoke(app, ["bootstrap-scan", str(target_repo)])

    result = runner.invoke(app, ["bootstrap-observe", "--repo-path", str(target_repo)])
    assert result.exit_code == 0, result.output

    repo = CodeUnitRepository()
    cancel_order = repo.find_current(neo4j_session, "orders.py", "orders.cancel_order")
    behavior_ids = outgoing_ids(neo4j_session, cancel_order.id, "EVIDENCES")
    assert behavior_ids

    behavior = ObservedBehaviorRepository().get(neo4j_session, behavior_ids[0])
    assert behavior.evidence_type == "documentation"
    assert "already shipped" in behavior.observed


def _reverse_analyst_output(subject: str) -> ReverseAnalystOutput:
    return ReverseAnalystOutput(
        requirement=CandidateRequirementDraft(text=f"candidate requirement for {subject}"),
        contract=ContractDraft(
            preconditions=["p"],
            postconditions=["q"],
            acceptance=[AcceptanceCriterionDraft(given="g", when="w", then="t")],
        ),
        examples=[
            ExampleDraft(input={"a": 1}, expected_output={"b": 2}, edge_case=False, behavioral_signature=BehavioralSignatureDraft()),
            ExampleDraft(input={"a": 0}, expected_output={"b": 0}, edge_case=True, behavioral_signature=BehavioralSignatureDraft()),
            ExampleDraft(input={"a": -1}, expected_output={"b": -2}, edge_case=True, behavioral_signature=BehavioralSignatureDraft()),
        ],
        rationale=f"grouped evidence for {subject}",
    )


def test_bootstrap_infer_groups_by_evidencing_file_path(neo4j_session, project_root, target_repo, fake_anthropic):
    _git_init_and_commit(target_repo)
    runner.invoke(app, ["bootstrap-scan", str(target_repo)])
    runner.invoke(app, ["bootstrap-observe", "--repo-path", str(target_repo)])

    # everything evidenced from this fixture repo shares one file path ("orders.py"
    # for docstring evidence, "test_orders.py" for test evidence) — two groups expected.
    fake_anthropic(responses=[_reverse_analyst_output("group-a"), _reverse_analyst_output("group-b")])

    result = runner.invoke(app, ["bootstrap-infer"])
    assert result.exit_code == 0, result.output
    assert "2 candidate Requirement/Contract group(s)" in result.output
