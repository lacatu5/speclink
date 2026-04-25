from __future__ import annotations

from pathlib import Path

from speclink.preprocessing.code_extraction import (
    EXTRACTORS,
    _PYTHON_CONFIG,
    _TYPESCRIPT_CONFIG,
    extract,
)


def test_extract_python_functions():
    source = b"def hello():\n    return 'world'\n\ndef goodbye():\n    return 'bye'\n"
    result = extract(source, Path("test.py"), Path("."), _PYTHON_CONFIG)
    names = {s["name"] for s in result["symbols"]}
    assert "hello" in names
    assert "goodbye" in names


def test_extract_python_class_with_methods():
    source = b"class UserService:\n    def get_user(self, id):\n        return id\n\n    def delete_user(self, id):\n        pass\n"
    result = extract(source, Path("service.py"), Path("."), _PYTHON_CONFIG)
    symbols = result["symbols"]
    names = {s["name"] for s in symbols}
    assert "UserService" in names
    assert "get_user" in names
    assert "delete_user" in names

    method = next(s for s in symbols if s["name"] == "get_user")
    assert "UserService" in method["id"]
    assert "def get_user(self, id):" in method["signature"]


def test_extract_python_methods_not_duplicated_as_functions():
    source = b"class Foo:\n    def bar(self):\n        pass\n"
    result = extract(source, Path("foo.py"), Path("."), _PYTHON_CONFIG)
    bar_symbols = [s for s in result["symbols"] if s["name"] == "bar"]
    assert len(bar_symbols) == 1


def test_extract_python_function_signature_excludes_body():
    source = b"def add(a, b):\n    return a + b\n"
    result = extract(source, Path("math.py"), Path("."), _PYTHON_CONFIG)
    func = next(s for s in result["symbols"] if s["name"] == "add")
    assert "return a + b" not in func["signature"]
    assert "def add(a, b):" in func["signature"]


def test_extract_typescript_interface():
    source = b"interface User {\n  name: string;\n  age: number;\n}\n"
    result = extract(source, Path("types.ts"), Path("."), _TYPESCRIPT_CONFIG)
    names = {s["name"] for s in result["symbols"]}
    assert "User" in names


def test_extract_typescript_enum():
    source = b"enum Color {\n  Red,\n  Green,\n  Blue,\n}\n"
    result = extract(source, Path("enums.ts"), Path("."), _TYPESCRIPT_CONFIG)
    names = {s["name"] for s in result["symbols"]}
    assert "Color" in names


def test_extract_typescript_type_alias():
    source = b"type UserID = string | number;\n"
    result = extract(source, Path("types.ts"), Path("."), _TYPESCRIPT_CONFIG)
    names = {s["name"] for s in result["symbols"]}
    assert "UserID" in names


def test_extract_typescript_variables():
    source = b"const x = 1;\nlet y = 2;\n"
    result = extract(source, Path("vars.ts"), Path("."), _TYPESCRIPT_CONFIG)
    assert len(result["variables"]) > 0


def test_extract_typescript_export_variables():
    source = b"export const API_URL = 'http://localhost';\n"
    result = extract(source, Path("config.ts"), Path("."), _TYPESCRIPT_CONFIG)
    assert len(result["variables"]) > 0


def test_extract_empty_source():
    result = extract(b"", Path("empty.py"), Path("."), _PYTHON_CONFIG)
    assert result["symbols"] == []


def test_extractors_dict_has_all_languages():
    assert "python" in EXTRACTORS
    assert "typescript" in EXTRACTORS
    assert "javascript" in EXTRACTORS
