from __future__ import annotations

from speclink.core.models import Classification, CodeElement, Section
from speclink.retrieval.stages import (
    _build_sig_map,
    _top_files_by_rerank,
    build_doc_map,
    group_by_heading,
)


def _make_section(heading: str, file_path: str, chunk_index: int = 0, hash: str = "h") -> Section:
    return Section(heading=heading, file_path=file_path, chunk_index=chunk_index, hash=hash)


class TestGroupByHeading:
    def test_groups_by_file_heading_chunk(self):
        s1 = _make_section("H1", "a.md", 0)
        s2 = _make_section("H1", "a.md", 1)
        s3 = _make_section("H2", "a.md", 0)
        result = group_by_heading([s1, s2, s3])
        assert len(result[("a.md", "H1", 0)]) == 1
        assert len(result[("a.md", "H1", 1)]) == 1
        assert len(result[("a.md", "H2", 0)]) == 1


class TestTopFilesByRerank:
    def test_empty_scores_returns_all(self, mock_config):
        file_ids = ["a.py", "b.py", "c.py"]
        result = _top_files_by_rerank({}, file_ids, "H1", mock_config)
        assert result == file_ids

    def test_filters_by_rerank_floor(self, mock_config):
        mock_config.rerank_floor = 0.5
        mock_config.rerank_gap = 999.0
        scores = {"a.py": 0.9, "b.py": 0.3, "c.py": 0.7}
        result = _top_files_by_rerank(scores, ["a.py", "b.py", "c.py"], "H1", mock_config)
        assert "a.py" in result
        assert "c.py" in result
        assert "b.py" not in result

    def test_applies_gap_threshold(self, mock_config):
        mock_config.rerank_floor = 0.0
        mock_config.rerank_gap = 0.15
        scores = {"a.py": 0.95, "b.py": 0.85, "c.py": 0.30}
        result = _top_files_by_rerank(scores, ["a.py", "b.py", "c.py"], "H1", mock_config)
        assert result == ["a.py", "b.py"]


class TestBuildSigMap:
    def test_groups_by_file_path(self):
        symbols = [
            CodeElement(id="a.py::f1", name="f1", signature="def f1()", code="", file_path="a.py"),
            CodeElement(id="a.py::f2", name="f2", signature="def f2()", code="", file_path="a.py"),
            CodeElement(id="b.py::g1", name="g1", signature="def g1()", code="", file_path="b.py"),
        ]
        result = _build_sig_map(symbols)
        assert len(result["a.py"]) == 2
        assert len(result["b.py"]) == 1

    def test_empty_symbols_returns_empty(self):
        assert _build_sig_map([]) == {}
        assert _build_sig_map(None) == {}

    def test_code_starting_with_signature_includes_body(self):
        sym = CodeElement(
            id="a.py::f",
            name="f",
            signature="def f():",
            code="def f():\n    return 1\n    extra",
            file_path="a.py",
        )
        result = _build_sig_map([sym])
        entry = result["a.py"][0]
        assert "def f():" in entry
        assert "return 1" in entry


class TestBuildDocMap:
    def test_creates_correct_structure(self):
        s1 = _make_section("H1", "docs/a.md", 0)
        s2 = _make_section("H2", "docs/a.md", 0)
        s3 = _make_section("H1", "docs/b.md", 0)
        h2f = {
            ("docs/a.md", "H1", 0): ["src/x.py"],
            ("docs/a.md", "H2", 0): ["src/y.py"],
            ("docs/b.md", "H1", 0): ["src/z.py"],
        }
        h2c = {
            ("docs/a.md", "H1", 0): [Classification(target_id="file:src/x.py", is_match=True)],
            ("docs/a.md", "H2", 0): [Classification(target_id="file:src/y.py", is_match=True)],
            ("docs/b.md", "H1", 0): [Classification(target_id="file:src/z.py", is_match=True)],
        }
        doc_map = build_doc_map(h2f, [s1, s2, s3], h2c)
        assert len(doc_map.mappings) == 2
        a_map = next(m for m in doc_map.mappings if m.doc_file == "docs/a.md")
        assert len(a_map.sections) == 2
        assert a_map.sections[0].files == ["src/x.py"]
