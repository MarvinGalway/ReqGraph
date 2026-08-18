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
from reqgraph.llm.roles import RoleConfig, resolve_model

T = TypeVar("T", bound=BaseModel)


class RoleInvocationError(RuntimeError):
    pass


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
    client = get_client()
    model = resolve_model(role)
    kwargs: dict[str, Any] = {}
    if role.effort:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": role.effort}
    if role.temperature is not None:
        kwargs["temperature"] = role.temperature

    current_prompt = user_prompt
    last_error: str | None = None
    for _ in range(max_retries + 1):
        message = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": current_prompt}],
            output_format=output_model,
            **kwargs,
        )
        parsed = message.parsed_output
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
