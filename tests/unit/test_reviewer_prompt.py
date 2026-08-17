from __future__ import annotations

from reqgraph.llm.prompts import reviewer
from reqgraph.llm.roles import ROLES


def test_reviewer_role_registered_distinct_from_other_roles():
    assert "reviewer" in ROLES
    assert ROLES["reviewer"].name == "reviewer"


def test_system_prompt_mentions_role_name():
    prompt = reviewer.system_prompt()
    assert "'reviewer'" in prompt


def test_user_prompt_includes_all_sections():
    prompt = reviewer.user_prompt(
        contract_text="pre=[] post=[]",
        requirement_text="users can cancel orders",
        codeunit_sources=["# a.py:cancel_order\ndef cancel_order(): ..."],
        test_sources=["# test_a.py:test_cancel\ndef test_cancel(): ..."],
    )
    assert "users can cancel orders" in prompt
    assert "pre=[] post=[]" in prompt
    assert "cancel_order" in prompt
    assert "test_cancel" in prompt


def test_user_prompt_handles_no_sources():
    prompt = reviewer.user_prompt("contract", "requirement", [], [])
    assert "contract" in prompt
    assert "requirement" in prompt
