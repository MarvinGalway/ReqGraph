from __future__ import annotations

import pytest
from pydantic import BaseModel

from reqgraph.llm.invoke import RoleInvocationError, invoke_role
from reqgraph.llm.roles import ROLES


class DummyOutput(BaseModel):
    value: int


def test_invoke_role_returns_parsed_output_on_success(fake_anthropic):
    fake = fake_anthropic(responses=[DummyOutput(value=3)])
    result = invoke_role(ROLES["critic"], "system", "user", DummyOutput)
    assert result.value == 3
    assert len(fake.messages.calls) == 1
    call = fake.messages.calls[0]
    assert call["output_format"] is DummyOutput
    assert call["output_config"] == {"effort": "high"}
    assert call["thinking"] == {"type": "adaptive"}


def test_invoke_role_uses_temperature_for_legacy_role(fake_anthropic):
    fake_anthropic(responses=[DummyOutput(value=1)])
    invoke_role(ROLES["librarian"], "system", "user", DummyOutput)


def test_invoke_role_retries_once_on_gate_failure_then_succeeds(fake_anthropic):
    fake = fake_anthropic(responses=[DummyOutput(value=1), DummyOutput(value=99)])

    def validate(output: DummyOutput) -> str | None:
        return None if output.value == 99 else "value must be 99"

    result = invoke_role(ROLES["critic"], "system", "user", DummyOutput, validate=validate)
    assert result.value == 99
    assert len(fake.messages.calls) == 2
    assert "rejected" in fake.messages.calls[1]["messages"][0]["content"]


def test_invoke_role_raises_after_exhausting_retries(fake_anthropic):
    fake_anthropic(responses=[DummyOutput(value=1), DummyOutput(value=2)])

    def always_fail(output: DummyOutput) -> str | None:
        return "never good enough"

    with pytest.raises(RoleInvocationError):
        invoke_role(ROLES["critic"], "system", "user", DummyOutput, validate=always_fail, max_retries=1)


def test_invoke_role_raises_when_response_unparseable(fake_anthropic):
    fake_anthropic(responses=[None, None])
    with pytest.raises(RoleInvocationError):
        invoke_role(ROLES["critic"], "system", "user", DummyOutput, max_retries=1)


def test_invoke_role_uses_openai_responses_api_when_role_provider_is_openai(
    monkeypatch, fake_openai
):
    monkeypatch.setenv("REQGRAPH_PROVIDER_CRITIC", "openai")
    fake = fake_openai(responses=[DummyOutput(value=7)])
    result = invoke_role(ROLES["critic"], "system", "user", DummyOutput)
    assert result.value == 7
    call = fake.responses.calls[0]
    assert call["text_format"] is DummyOutput
    assert call["instructions"] == "system"
    assert call["input"] == "user"
    assert call["reasoning"] == {"effort": "high"}
    assert call["model"] == "gpt-5.1"


def test_invoke_role_global_provider_override_applies_to_all_roles(monkeypatch, fake_openai):
    monkeypatch.setenv("REQGRAPH_PROVIDER", "openai")
    fake = fake_openai(responses=[DummyOutput(value=1)])
    invoke_role(ROLES["librarian"], "system", "user", DummyOutput)
    assert fake.responses.calls[0]["model"] == "gpt-5.1-mini"


def test_invoke_role_per_role_model_override_wins_over_provider_default(
    monkeypatch, fake_openai
):
    monkeypatch.setenv("REQGRAPH_PROVIDER_CRITIC", "openai")
    monkeypatch.setenv("REQGRAPH_MODEL_CRITIC", "gpt-5.1-custom")
    fake = fake_openai(responses=[DummyOutput(value=1)])
    invoke_role(ROLES["critic"], "system", "user", DummyOutput)
    assert fake.responses.calls[0]["model"] == "gpt-5.1-custom"
