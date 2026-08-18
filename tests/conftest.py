from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"
FIXTURE_REPO_JS = Path(__file__).parent / "fixtures" / "sample_repo_js"

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


# Any test fixture in this suite creates at most a handful of nodes. A count
# above this is a signal that NEO4J_URI points at something other than a
# disposable test instance — e.g. a real bootstrapped project's graph, which
# happened once: a `pytest -m integration` run destroyed a project's 827-node
# graph because Community Edition's single-database limit meant it shared the
# same instance as this repo's tests. See `_guard_against_wiping_real_data`.
_MAX_PLAUSIBLE_TEST_NODES = 50


def _guard_against_wiping_real_data(sess) -> None:
    if os.environ.get("REQGRAPH_ALLOW_TEST_WIPE") == "1":
        return
    count = sess.run("MATCH (n) RETURN count(n) AS n").single()["n"]
    if count > _MAX_PLAUSIBLE_TEST_NODES:
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        pytest.fail(
            f"Refusing to wipe Neo4j at {uri}: found {count} nodes, more than any test fixture "
            f"in this suite would ever create ({_MAX_PLAUSIBLE_TEST_NODES}). This looks like a "
            "real project's graph, not a disposable test instance — point NEO4J_URI/"
            "NEO4J_DATABASE at a dedicated test instance instead. If you're certain it's safe "
            "to wipe, set REQGRAPH_ALLOW_TEST_WIPE=1."
        )


@pytest.fixture
def neo4j_session():
    """A live Neo4j session, wiped clean before use. Skips the test if Neo4j
    is unreachable (Community Edition — no isolated test database, so we
    wipe instead of using a second database).
    """
    if not driver_module.verify_connectivity():
        pytest.skip("Neo4j is not reachable (docker compose up -d neo4j)")
    with driver_module.session() as sess:
        _guard_against_wiping_real_data(sess)
        sess.run("MATCH (n) DETACH DELETE n")
        apply_schema(sess, with_vector=False)
        yield sess
        sess.run("MATCH (n) DETACH DELETE n")


@pytest.fixture
def project_root(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def target_repo(tmp_path) -> Path:
    """A throwaway copy of the orders.py/test_orders.py fixture repo (spec
    §15 Slice B) for commands that read/run code from a target repository.
    """
    dest = tmp_path / "target_repo"
    shutil.copytree(FIXTURE_REPO, dest)
    return dest


@pytest.fixture
def target_repo_js(tmp_path) -> Path:
    """A throwaway copy of the orders.js/orders.test.js fixture repo, the
    JS/TS mirror of `target_repo`, for cross-language extraction tests.
    """
    dest = tmp_path / "target_repo_js"
    shutil.copytree(FIXTURE_REPO_JS, dest)
    return dest


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
    """Patches reqgraph.llm.client.get_client to return a FakeAnthropicClient
    for the 'anthropic' provider. Call `fake_anthropic(responses=[...])` to
    configure the canned outputs.
    """

    def _install(responses):
        fake = FakeAnthropicClient(responses)
        monkeypatch.setattr(llm_client_module, "get_client", lambda provider="anthropic": fake)
        monkeypatch.setattr(llm_invoke_module, "get_client", lambda provider="anthropic": fake)
        return fake

    return _install


class FakeResponses:
    def __init__(self, responses):
        # responses: list of pydantic model instances (or None to simulate a parse failure),
        # consumed in order across calls.
        self._responses = list(responses)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeResponses.parse called more times than responses provided")
        return FakeParsedResponse(self._responses.pop(0))


class FakeParsedResponse:
    def __init__(self, output_parsed):
        self.output_parsed = output_parsed


class FakeOpenAIClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


@pytest.fixture
def fake_openai(monkeypatch):
    """Patches reqgraph.llm.client.get_client to return a FakeOpenAIClient for
    the 'openai' provider — mirrors `fake_anthropic` but for `client.responses.parse`.
    """

    def _install(responses):
        fake = FakeOpenAIClient(responses)
        monkeypatch.setattr(llm_client_module, "get_client", lambda provider="anthropic": fake)
        monkeypatch.setattr(llm_invoke_module, "get_client", lambda provider="anthropic": fake)
        return fake

    return _install
