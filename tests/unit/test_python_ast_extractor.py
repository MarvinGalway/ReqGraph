from __future__ import annotations

from reqgraph.extract.python_ast import PythonExtractor

SOURCE = '''
import os
from pkg import thing

def add(a, b):
    return a + b

class Foo:
    def bar(self):
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
