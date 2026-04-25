from __future__ import annotations

from pathlib import Path

from speclink.preprocessing.code import CodePreprocessor, FilePreprocessor, collect_signatures_and_bodies


class TestCodePreprocessorPipeline:
    def test_extracts_symbols(self, mini_project: Path):
        preprocessor = CodePreprocessor()
        elements = preprocessor.process_codebase(mini_project / "src")
        names = [e.name for e in elements]
        assert "get_user" in names
        assert "create_user" in names
        assert any("api.py" in e.file_path for e in elements)

    def test_file_preprocessor_extracts_files(self, mini_project: Path):
        preprocessor = FilePreprocessor()
        elements = preprocessor.process_codebase(mini_project / "src")
        paths = [e.file_path for e in elements]
        assert any("api.py" in p for p in paths)
        assert all(e.id.startswith("file:") for e in elements)

    def test_code_preprocessor_ignores_gitignored(self, git_repo: Path):
        (git_repo / ".gitignore").write_text("vendor/\n")
        vendor = git_repo / "vendor"
        vendor.mkdir()
        (vendor / "lib.py").write_text("def hidden(): pass\n")
        preprocessor = CodePreprocessor()
        elements = preprocessor.process_codebase(git_repo)
        assert all("vendor" not in e.file_path for e in elements)

    def test_collect_signatures_and_bodies_pipeline(self, mini_project: Path):
        preprocessor = CodePreprocessor()
        symbols = preprocessor.process_codebase(mini_project / "src")
        results = collect_signatures_and_bodies(symbols)
        assert len(results) > 0
        assert all("name" in r for r in results)
        assert any("get_user" in r.get("signature", "") for r in results)
