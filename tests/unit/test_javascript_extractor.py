from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_javascript")

from reqgraph.extract.javascript_ts import JavaScriptExtractor

SOURCE = """
function helper(x) { return x + 1; }

function add(a, b) { return helper(a) + helper(b); }

const mul = (a, b) => a * b;

class Foo {
  bar() { return this.baz(); }
  baz() { return 1; }
}

import { thing } from "pkg";
"""

TEST_SOURCE = """
import { describe, it, expect } from "vitest";
import { add } from "./mod";

describe("add", () => {
  it("works for positive numbers", () => {
    expect(add(1, 2)).toBe(3);
  });
  it("works for negative numbers", () => {
    expect(add(-1, -2)).toBe(-3);
  });
});

test("a standalone test", () => {
  expect(1).toBe(1);
});
"""

TS_SOURCE = """
function greet(name: string): string {
  return `hello ${name}`;
}
"""


def test_extracts_functions_arrow_functions_and_classes_with_qualnames():
    result = JavaScriptExtractor().extract("src/mod.js", SOURCE)
    symbols = {c.symbol: c.kind for c in result.codeunits}
    assert symbols["src.mod.helper"] == "function"
    assert symbols["src.mod.add"] == "function"
    assert symbols["src.mod.mul"] == "function"  # const x = () => {} arrow function
    assert symbols["src.mod.Foo"] == "class"
    assert symbols["src.mod.Foo.bar"] == "method"
    assert symbols["src.mod.Foo.baz"] == "method"


def test_all_extracted_symbols_are_tagged_javascript():
    result = JavaScriptExtractor().extract("src/mod.js", SOURCE)
    assert all(c.language == "javascript" for c in result.codeunits)


def test_extracts_module_level_imports():
    result = JavaScriptExtractor().extract("src/mod.js", SOURCE)
    assert {i.imports for i in result.imports} == {"pkg"}


def test_call_graph_resolves_top_level_function_calls():
    result = JavaScriptExtractor().extract("src/mod.js", SOURCE)
    pairs = {(c.caller_symbol, c.callee_symbol) for c in result.calls}
    assert ("src.mod.add", "src.mod.helper") in pairs


def test_call_graph_resolves_this_method_calls():
    result = JavaScriptExtractor().extract("src/mod.js", SOURCE)
    pairs = {(c.caller_symbol, c.callee_symbol) for c in result.calls}
    assert ("src.mod.Foo.bar", "src.mod.Foo.baz") in pairs


def test_hash_is_symbol_level_not_file_level():
    original = JavaScriptExtractor().extract("src/mod.js", SOURCE)
    changed = JavaScriptExtractor().extract("src/mod.js", SOURCE.replace("return x + 1;", "return x + 2;"))
    original_hashes = {c.symbol: c.hash for c in original.codeunits}
    changed_hashes = {c.symbol: c.hash for c in changed.codeunits}
    assert original_hashes["src.mod.helper"] != changed_hashes["src.mod.helper"]
    assert original_hashes["src.mod.add"] == changed_hashes["src.mod.add"]


def test_detects_it_and_test_callback_style_tests_with_slugified_names():
    result = JavaScriptExtractor().extract("src/mod.test.js", TEST_SOURCE)
    symbols = {t.symbol for t in result.tests}
    assert symbols == {
        "src.mod.test.works_for_positive_numbers",
        "src.mod.test.works_for_negative_numbers",
        "src.mod.test.a_standalone_test",
    }
    assert all(t.framework == "vitest" for t in result.tests)


def test_non_test_file_does_not_extract_it_test_callbacks_as_tests():
    result = JavaScriptExtractor().extract("src/mod.js", TEST_SOURCE)
    assert result.tests == []


def test_typescript_file_uses_typescript_grammar():
    result = JavaScriptExtractor().extract("src/mod.ts", TS_SOURCE)
    symbols = {c.symbol for c in result.codeunits}
    assert "src.mod.greet" in symbols


def test_syntax_error_returns_empty_result_not_raise():
    result = JavaScriptExtractor().extract("broken.js", "function f( {\n")
    assert result.codeunits == []
    assert result.tests == []
