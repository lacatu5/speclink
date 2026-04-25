from __future__ import annotations

from speclink.core.models import CodeElement
from speclink.preprocessing.code import (
    CodePreprocessor,
    FilePreprocessor,
    collect_signatures_and_bodies,
    load_gitignore,
)


def test_collect_filters_empty():
    symbols = [
        CodeElement(id="a::x", name="x", signature="", code="", file_path="a.py"),
        CodeElement(id="a::y", name="y", signature="def y()", code="", file_path="a.py"),
    ]
    result = collect_signatures_and_bodies(symbols)
    assert len(result) == 1
    assert result[0]["name"] == "y"


def test_collect_with_body():
    symbols = [
        CodeElement(
            id="a::f", name="f", signature="def f()", code="def f(): pass", file_path="a.py"
        ),
    ]
    result = collect_signatures_and_bodies(symbols)
    assert result[0]["body_sample"] == "def f(): pass"
    assert result[0]["signature"] == "def f()"


def test_collect_signature_fallback_to_name():
    symbols = [
        CodeElement(id="a::g", name="g", signature="", code="x = 1", file_path="a.py"),
    ]
    result = collect_signatures_and_bodies(symbols)
    assert result[0]["signature"] == "g"


def test_load_gitignore(git_repo):
    (git_repo / ".gitignore").write_text("*.log\nnode_modules/\n")
    spec = load_gitignore(git_repo)
    assert spec.match_file("debug.log")
    assert spec.match_file("node_modules/foo.js")
    assert not spec.match_file("src/main.py")


def test_code_preprocessor(mini_project):
    cp = CodePreprocessor()
    elements = cp.process_codebase(mini_project)
    assert len(elements) > 0
    names = {e.name for e in elements}
    assert "get_user" in names
    assert "create_user" in names


def test_file_preprocessor(mini_project):
    fp = FilePreprocessor()
    elements = fp.process_codebase(mini_project)
    assert len(elements) > 0
    ids = {e.id for e in elements}
    assert any("api.py" in i for i in ids)


def test_code_preprocessor_variables_map(mini_project):
    cp = CodePreprocessor()
    cp.process_codebase(mini_project)
    assert isinstance(cp.variables_map, dict)


def test_code_preprocessor_empty_dir(tmp_path):
    cp = CodePreprocessor()
    result = cp.process_codebase(tmp_path)
    assert result == []


def test_code_preprocessor_with_gitignore(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True, check=True)

    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text("def get_user(): pass\n")
    (tmp_path / ".gitignore").write_text("src/\n")

    cp = CodePreprocessor()
    result = cp.process_codebase(tmp_path)
    assert len(result) == 0


def test_file_preprocessor_with_gitignore(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True, check=True)

    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text("def get_user(): pass\n")
    (tmp_path / ".gitignore").write_text("src/\n")

    fp = FilePreprocessor()
    result = fp.process_codebase(tmp_path)
    assert len(result) == 0


def test_file_preprocessor_ignores_non_code(tmp_path):
    (tmp_path / "readme.txt").write_text("not code")
    (tmp_path / "data.json").write_text("{}")
    fp = FilePreprocessor()
    result = fp.process_codebase(tmp_path)
    assert len(result) == 0
