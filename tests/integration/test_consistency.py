from __future__ import annotations

import pytest

from reqgraph.graph.consistency import run_consistency_checks
from reqgraph.graph.models import Contract, Requirement
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.contract import ContractRepository
from reqgraph.graph.repositories.requirement import RequirementRepository

pytestmark = pytest.mark.integration


def test_clean_graph_has_no_violations(neo4j_session, project_root):
    violations = run_consistency_checks(neo4j_session, project_root)
    assert violations == []


def test_check1_validated_requirement_without_validated_contract(neo4j_session, project_root):
    req_repo = RequirementRepository()
    req = Requirement(text="orphan", knowledge_status="validated")
    req_repo.create(neo4j_session, req)

    violations = run_consistency_checks(neo4j_session, project_root)
    ids_by_check = {v.check_id: v.node_id for v in violations}
    assert ids_by_check.get("1") == req.id


def test_check2_validated_contract_without_minimum_coverage(neo4j_session, project_root):
    contract_repo = ContractRepository()
    contract = Contract(knowledge_status="validated")
    contract_repo.create(neo4j_session, contract)

    violations = run_consistency_checks(neo4j_session, project_root)
    matches = [v for v in violations if v.check_id == "2" and v.node_id == contract.id]
    assert len(matches) == 1
    assert "examples=0" in matches[0].detail


def test_check9_open_contradicts_edge(neo4j_session, project_root):
    req_repo = RequirementRepository()
    r1 = Requirement(text="r1")
    r2 = Requirement(text="r2")
    req_repo.create(neo4j_session, r1)
    req_repo.create(neo4j_session, r2)
    edges.contradicts(neo4j_session, r1.id, r2.id, status="open")

    violations = run_consistency_checks(neo4j_session, project_root)
    matches = [v for v in violations if v.check_id == "9"]
    assert len(matches) == 1
    assert matches[0].node_id == r1.id


def test_check10_legacy_validated_without_human_review(neo4j_session, project_root):
    req_repo = RequirementRepository()
    req = Requirement(
        text="inferred",
        knowledge_status="validated",
        origin_mode="legacy-bootstrap",
        trust="external-unverified",
    )
    req_repo.create(neo4j_session, req)

    violations = run_consistency_checks(neo4j_session, project_root)
    matches = [v for v in violations if v.check_id == "10" and v.node_id == req.id]
    assert len(matches) == 1
