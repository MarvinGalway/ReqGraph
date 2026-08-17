from __future__ import annotations

import os
from pathlib import Path

import pytest

from reqgraph.config import reset_settings_cache
from reqgraph.graph import driver as driver_module
from reqgraph.graph.schema import apply_schema
from reqgraph.llm import client as llm_client_module
from reqgraph.llm import invoke as llm_invoke_module


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    """Every test gets its own project-state root and a reset settings/driver/client cache."""
    monkeypatch.setenv("REQGRAPH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "reqgraph-dev"))
    reset_settings_cache()
    driver_module.close_driver()
    llm_client_module.reset_client_cache()
    yield
    reset_settings_cache()
    driver_module.close_driver()
    llm_client_module.reset_client_cache()


@pytest.fixture
def neo4j_session():
    """A live Neo4j session, wiped clean before use. Skips the test if Neo4j
    is unreachable (Community Edition — no isolated test database, so we
    wipe instead of using a second database).
    """
    if not driver_module.verify_connectivity():
        pytest.skip("Neo4j is not reachable (docker compose up -d neo4j)")
    with driver_module.session() as sess:
        sess.run("MATCH (n) DETACH DELETE n")
        apply_schema(sess, with_vector=False)
        yield sess
        sess.run("MATCH (n) DETACH DELETE n")


@pytest.fixture
def project_root(tmp_path) -> Path:
    return tmp_path


class FakeParsedMessage:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class FakeMessages:
    def __init__(self, responses):
        # responses: list of pydantic model instances (or None to simulate a parse failure),
        # consumed in order across calls.
        self._responses = list(responses)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages.parse called more times than responses provided")
        return FakeParsedMessage(self._responses.pop(0))


class FakeAnthropicClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Patches reqgraph.llm.client.get_client to return a FakeAnthropicClient.
    Call `fake_anthropic(responses=[...])` to configure the canned outputs.
    """

    def _install(responses):
        fake = FakeAnthropicClient(responses)
        monkeypatch.setattr(llm_client_module, "get_client", lambda: fake)
        monkeypatch.setattr(llm_invoke_module, "get_client", lambda: fake)
        return fake

    return _install
