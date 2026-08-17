"""Single place CLI commands import repository instances from."""

from __future__ import annotations

from reqgraph.graph.repositories.assumption import AssumptionRepository
from reqgraph.graph.repositories.clarification import ClarificationRepository
from reqgraph.graph.repositories.codeunit import CodeUnitRepository
from reqgraph.graph.repositories.configunit import ConfigUnitRepository
from reqgraph.graph.repositories.contract import ContractRepository
from reqgraph.graph.repositories.example import ExampleRepository
from reqgraph.graph.repositories.issue import IssueRepository
from reqgraph.graph.repositories.observed_behavior import ObservedBehaviorRepository
from reqgraph.graph.repositories.requirement import RequirementRepository
from reqgraph.graph.repositories.task import TaskRepository
from reqgraph.graph.repositories.test import TestRepository

requirements = RequirementRepository()
clarifications = ClarificationRepository()
assumptions = AssumptionRepository()
contracts = ContractRepository()
examples = ExampleRepository()
tasks = TaskRepository()
codeunits = CodeUnitRepository()
configunits = ConfigUnitRepository()
tests = TestRepository()
issues = IssueRepository()
observed_behaviors = ObservedBehaviorRepository()
