from __future__ import annotations

from reqgraph.extract.python_ast import (
    PythonExtractor,
    extract_symbol_docstring,
    extract_symbol_source,
)

SOURCE = '''
import os
from pkg import thing

def add(a, b):
    return a + b

class Foo:
    def bar(self):
        return 1
'''

CALL_SOURCE = '''
def helper(x):
    return x + 1

def add(a, b):
    return helper(a) + helper(b)

class Foo:
    def bar(self):
        return self.baz()

    def baz(self):
        return 1

def unrelated():
    import os
    return os.getcwd()
'''

DOCSTRING_SOURCE = '''
def add(a, b):
    """Adds two numbers."""
    return a + b

def no_doc(a):
    return a

class Foo:
    def bar(self):
        """Returns one."""
        return 1
'''

TEST_SOURCE = '''
import pytest

def test_add():
    assert add(1, 2) == 3

def test_add_raises():
    with pytest.raises(TypeError):
        add(None, None)
'''


def test_extracts_functions_classes_methods_with_qualnames():
    result = PythonExtractor().extract("pkg/mod.py", SOURCE)
    symbols = {c.symbol: c.kind for c in result.codeunits}
    assert symbols["pkg.mod.add"] == "function"
    assert symbols["pkg.mod.Foo"] == "class"
    assert symbols["pkg.mod.Foo.bar"] == "method"


def test_extracts_module_level_imports():
    result = PythonExtractor().extract("pkg/mod.py", SOURCE)
    imports = {i.imports for i in result.imports}
    assert imports == {"os", "pkg"}


def test_test_functions_only_detected_in_test_named_files():
    non_test_result = PythonExtractor().extract("pkg/mod.py", TEST_SOURCE)
    assert non_test_result.tests == []
    assert any(c.symbol == "pkg.mod.test_add" for c in non_test_result.codeunits)

    test_result = PythonExtractor().extract("pkg/test_mod.py", TEST_SOURCE)
    test_symbols = {t.symbol for t in test_result.tests}
    assert test_symbols == {"pkg.test_mod.test_add", "pkg.test_mod.test_add_raises"}
    assert all(t.framework == "pytest" for t in test_result.tests)


def test_hash_is_symbol_level_not_file_level():
    original = PythonExtractor().extract("pkg/mod.py", SOURCE)
    changed_source = SOURCE.replace("return a + b", "return a + b + 0")
    changed = PythonExtractor().extract("pkg/mod.py", changed_source)

    original_hashes = {c.symbol: c.hash for c in original.codeunits}
    changed_hashes = {c.symbol: c.hash for c in changed.codeunits}

    assert original_hashes["pkg.mod.add"] != changed_hashes["pkg.mod.add"]
    assert original_hashes["pkg.mod.Foo"] == changed_hashes["pkg.mod.Foo"]
    assert original_hashes["pkg.mod.Foo.bar"] == changed_hashes["pkg.mod.Foo.bar"]


def test_syntax_error_returns_empty_result_not_raise():
    result = PythonExtractor().extract("broken.py", "def f(:\n")
    assert result.codeunits == []
    assert result.tests == []


def test_extract_symbol_source_function_and_method():
    function_source = extract_symbol_source("pkg/mod.py", SOURCE, "pkg.mod.add")
    assert function_source == "def add(a, b):\n    return a + b"

    method_source = extract_symbol_source("pkg/mod.py", SOURCE, "pkg.mod.Foo.bar")
    assert method_source == "def bar(self):\n        return 1"


def test_extract_symbol_source_unknown_symbol_returns_none():
    assert extract_symbol_source("pkg/mod.py", SOURCE, "pkg.mod.missing") is None


def test_extract_symbol_source_syntax_error_returns_none():
    assert extract_symbol_source("broken.py", "def f(:\n", "broken.f") is None


def test_call_graph_resolves_top_level_function_calls():
    result = PythonExtractor().extract("pkg/mod.py", CALL_SOURCE)
    pairs = {(c.caller_symbol, c.callee_symbol) for c in result.calls}
    assert ("pkg.mod.add", "pkg.mod.helper") in pairs


def test_call_graph_resolves_self_method_calls():
    result = PythonExtractor().extract("pkg/mod.py", CALL_SOURCE)
    pairs = {(c.caller_symbol, c.callee_symbol) for c in result.calls}
    assert ("pkg.mod.Foo.bar", "pkg.mod.Foo.baz") in pairs


def test_call_graph_does_not_resolve_external_or_dotted_calls():
    result = PythonExtractor().extract("pkg/mod.py", CALL_SOURCE)
    callers = {c.caller_symbol for c in result.calls}
    # unrelated() only calls os.getcwd() — an external dotted call, unresolved
    assert "pkg.mod.unrelated" not in callers


def test_call_graph_multiple_call_sites_produce_multiple_entries():
    # add() calls helper() twice (helper(a), helper(b)) — both call sites recorded,
    # deduping (if desired) is the CLI layer's job, not the extractor's.
    result = PythonExtractor().extract("pkg/mod.py", CALL_SOURCE)
    matching = [c for c in result.calls if c.caller_symbol == "pkg.mod.add" and c.callee_symbol == "pkg.mod.helper"]
    assert len(matching) == 2


def test_extract_symbol_docstring_function_and_method():
    assert extract_symbol_docstring("pkg/mod.py", DOCSTRING_SOURCE, "pkg.mod.add") == "Adds two numbers."
    assert extract_symbol_docstring("pkg/mod.py", DOCSTRING_SOURCE, "pkg.mod.Foo.bar") == "Returns one."


def test_extract_symbol_docstring_absent_returns_none():
    assert extract_symbol_docstring("pkg/mod.py", DOCSTRING_SOURCE, "pkg.mod.no_doc") is None


def test_extract_symbol_docstring_unknown_symbol_returns_none():
    assert extract_symbol_docstring("pkg/mod.py", DOCSTRING_SOURCE, "pkg.mod.missing") is None
