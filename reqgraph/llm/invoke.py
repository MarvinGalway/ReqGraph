"""Role invocation: builds the API call from a RoleConfig, forces structured
output via `output_format=`, and retries once on a gate-condition failure the
JSON schema itself can't express (e.g. formalize's >=3 examples rule) before
raising a hard error — never a silent pass-through of a degenerate artifact.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from reqgraph.llm.client import get_client
from reqgraph.llm.roles import RoleConfig, resolve_model, resolve_provider

T = TypeVar("T", bound=BaseModel)


class RoleInvocationError(RuntimeError):
    pass


def _invoke_once(
    provider: str,
    client: Any,
    model: str,
    role: RoleConfig,
    system_prompt: str,
    user_prompt: str,
    output_model: type[T],
    max_tokens: int,
) -> T | None:
    if provider == "anthropic":
        kwargs: dict[str, Any] = {}
        if role.effort:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": role.effort}
        if role.temperature is not None:
            kwargs["temperature"] = role.temperature
        message = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=output_model,
            **kwargs,
        )
        return message.parsed_output
    elif provider == "openai":
        # Responses API structured-output parsing helper: `text_format=` mirrors
        # Anthropic's `output_format=`, `reasoning.effort` takes the same literal
        # values as `role.effort` (see roles.py docstring), and `.output_parsed`
        # mirrors `.parsed_output`.
        kwargs = {}
        if role.effort:
            kwargs["reasoning"] = {"effort": role.effort}
        if role.temperature is not None:
            kwargs["temperature"] = role.temperature
        response = client.responses.parse(
            model=model,
            max_output_tokens=max_tokens,
            instructions=system_prompt,
            input=user_prompt,
            text_format=output_model,
            **kwargs,
        )
        return response.output_parsed
    raise RoleInvocationError(f"Unknown LLM provider {provider!r} (supported: anthropic, openai)")


def invoke_role(
    role: RoleConfig,
    system_prompt: str,
    user_prompt: str,
    output_model: type[T],
    *,
    # Roles with `effort` set enable adaptive thinking, whose tokens share this
    # same budget with the final structured output — too low a default truncates
    # the JSON mid-response before thinking leaves it any room to finish.
    max_tokens: int = 16384,
    validate: Callable[[T], str | None] | None = None,
    max_retries: int = 1,
) -> T:
    """`validate`, if given, returns an error string on gate failure or None on success."""
    provider = resolve_provider(role)
    client = get_client(provider)
    model = resolve_model(role)

    current_prompt = user_prompt
    last_error: str | None = None
    for _ in range(max_retries + 1):
        parsed = _invoke_once(
            provider, client, model, role, system_prompt, current_prompt, output_model, max_tokens
        )
        if parsed is None:
            last_error = "model response could not be parsed into the requested schema"
        elif validate is not None:
            last_error = validate(parsed)
            if last_error is None:
                return parsed
        else:
            return parsed
        current_prompt = (
            f"{user_prompt}\n\nYour previous response was rejected: {last_error}\n"
            "Please correct it and respond again with the full structured output."
        )
    raise RoleInvocationError(
        f"{role.name} failed after {max_retries + 1} attempt(s): {last_error}"
    )
