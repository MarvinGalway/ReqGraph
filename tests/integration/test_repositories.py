from __future__ import annotations

import pytest

from reqgraph.graph.models import CodeUnit, Contract, Requirement, Task
from reqgraph.graph.repositories import edges
from reqgraph.graph.repositories.codeunit import CodeUnitRepository
from reqgraph.graph.repositories.contract import ContractRepository
from reqgraph.graph.repositories.requirement import RequirementRepository
from reqgraph.graph.repositories.task import TaskRepository

pytestmark = pytest.mark.integration


def test_requirement_create_and_get_round_trip(neo4j_session):
    repo = RequirementRepository()
    req = Requirement(text="Users can log in", source="document")
    repo.create(neo4j_session, req)

    loaded = repo.get(neo4j_session, req.id)
    assert loaded is not None
    assert loaded.text == "Users can log in"
    assert loaded.knowledge_status == "observed"


def test_contract_acceptance_json_field_round_trips(neo4j_session):
    repo = ContractRepository()
    contract = Contract(
        preconditions=["p1"],
        acceptance=[{"given": "g", "when": "w", "then": "t"}],
    )
    repo.create(neo4j_session, contract)

    loaded = repo.get(neo4j_session, contract.id)
    assert loaded.acceptance[0].given == "g"
    assert loaded.acceptance[0].then == "t"


def test_formalizes_edge_and_witnesses_and_derives_from(neo4j_session):
    req_repo = RequirementRepository()
    contract_repo = ContractRepository()
    task_repo = TaskRepository()

    req = Requirement(text="req")
    req_repo.create(neo4j_session, req)
    contract = Contract()
    contract_repo.create(neo4j_session, contract)
    edges.formalizes(neo4j_session, contract.id, req.id, generated_by="human")

    task = Task(title="do it")
    task_repo.create(neo4j_session, task)
    edges.derives_from(neo4j_session, task.id, contract.id)

    assert edges.edge_exists(neo4j_session, "FORMALIZES", contract.id, req.id)
    assert edges.edge_exists(neo4j_session, "DERIVES_FROM", task.id, contract.id)
    assert edges.outgoing_ids(neo4j_session, task.id, "DERIVES_FROM") == [contract.id]


def test_codeunit_create_version_supersedes_and_carries_forward_implements(neo4j_session):
    contract_repo = ContractRepository()
    codeunit_repo = CodeUnitRepository()

    contract = Contract()
    contract_repo.create(neo4j_session, contract)

    v1 = CodeUnit(path="a.py", symbol="a.f", hash="hash1")
    codeunit_repo.create(neo4j_session, v1)
    edges.implements(neo4j_session, v1.id, contract.id)

    v2 = CodeUnit(path="a.py", symbol="a.f", hash="hash2", verification_status="needs_revalidation")
    codeunit_repo.create_version(neo4j_session, v2, v1.id)

    assert edges.edge_exists(neo4j_session, "SUPERSEDES", v2.id, v1.id)
    assert edges.edge_exists(neo4j_session, "IMPLEMENTS", v2.id, contract.id)

    current = codeunit_repo.find_current(neo4j_session, "a.py", "a.f")
    assert current is not None
    assert current.id == v2.id
