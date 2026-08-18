from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_javascript")

from reqgraph.extract.javascript_ts import (
    JavaScriptExtractor,
    extract_symbol_docstring,
    extract_symbol_source,
)

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

EXPORT_SOURCE = """
export function QuizScreen(props) { return helper(props); }

export const mul = (a, b) => a * b;

export default class Foo {
  bar() { return this.baz(); }
  baz() { return 1; }
}

function helper(x) { return x + 1; }
"""

DOCUMENTED_EXPORT_SOURCE = """
/**
 * Renders the quiz screen.
 */
export function QuizScreen(props) { return props; }

/** Multiplies two numbers. */
export const mul = (a, b) => a * b;
"""

DOCUMENTED_SOURCE = """
/**
 * Adds two numbers.
 * @returns the sum
 */
function add(a, b) { return a + b; }

const mul = (a, b) => a * b;

class Foo {
  /** Computes bar. */
  bar() { return 1; }
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


def test_extract_symbol_source_returns_function_and_arrow_and_method_text():
    assert "return helper(a) + helper(b)" in extract_symbol_source("src/mod.js", SOURCE, "src.mod.add")
    assert "a * b" in extract_symbol_source("src/mod.js", SOURCE, "src.mod.mul")
    assert "this.baz()" in extract_symbol_source("src/mod.js", SOURCE, "src.mod.Foo.bar")


def test_extract_symbol_source_returns_none_for_unknown_symbol():
    assert extract_symbol_source("src/mod.js", SOURCE, "src.mod.nope") is None


def test_extract_symbol_docstring_reads_jsdoc_for_function_arrow_and_method():
    assert extract_symbol_docstring("src/mod.js", DOCUMENTED_SOURCE, "src.mod.add") == "Adds two numbers.\n@returns the sum"
    assert extract_symbol_docstring("src/mod.js", DOCUMENTED_SOURCE, "src.mod.Foo.bar") == "Computes bar."


def test_extract_symbol_docstring_none_when_no_leading_jsdoc():
    assert extract_symbol_docstring("src/mod.js", DOCUMENTED_SOURCE, "src.mod.mul") is None


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


def test_extracts_exported_function_const_and_default_class():
    # The most common shape in real JS/TS code — a top-level `export`/
    # `export default` on the symbol that matters — was previously invisible:
    # tree-sitter wraps it in an export_statement, which the extractor's
    # top-level-children loop didn't unwrap, so only private helpers like
    # `helper` below were ever found.
    result = JavaScriptExtractor().extract("src/mod.tsx", EXPORT_SOURCE)
    symbols = {c.symbol: c.kind for c in result.codeunits}
    assert symbols["src.mod.QuizScreen"] == "function"
    assert symbols["src.mod.mul"] == "function"
    assert symbols["src.mod.Foo"] == "class"
    assert symbols["src.mod.Foo.bar"] == "method"
    assert symbols["src.mod.helper"] == "function"


def test_call_graph_resolves_calls_from_an_exported_function():
    result = JavaScriptExtractor().extract("src/mod.tsx", EXPORT_SOURCE)
    pairs = {(c.caller_symbol, c.callee_symbol) for c in result.calls}
    assert ("src.mod.QuizScreen", "src.mod.helper") in pairs


def test_extract_symbol_source_finds_exported_symbols():
    assert "helper(props)" in extract_symbol_source("src/mod.tsx", EXPORT_SOURCE, "src.mod.QuizScreen")
    assert "a * b" in extract_symbol_source("src/mod.tsx", EXPORT_SOURCE, "src.mod.mul")


def test_extract_symbol_docstring_reads_jsdoc_preceding_an_export_statement():
    assert (
        extract_symbol_docstring("src/mod.tsx", DOCUMENTED_EXPORT_SOURCE, "src.mod.QuizScreen")
        == "Renders the quiz screen."
    )
    assert (
        extract_symbol_docstring("src/mod.tsx", DOCUMENTED_EXPORT_SOURCE, "src.mod.mul")
        == "Multiplies two numbers."
    )
