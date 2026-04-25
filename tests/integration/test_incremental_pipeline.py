from __future__ import annotations

from speclink.core.models import DocMap, Document, Section
from speclink.retrieval.incremental import ChangeDetection, detect_changes, merge_unchanged, resolve_from_cache
from speclink.retrieval.stages import PreprocessResult, RetrieveResult


def _section(heading: str, file_path: str, hash: str, chunk_index: int = 0) -> Section:
    return Section(
        heading=heading,
        content="content",
        file_path=file_path,
        hash=hash,
        chunk_index=chunk_index,
    )


class TestIncrementalPipeline:
    def test_detect_changes_full_pipeline(self):
        sec1 = _section("H1", "d.md", "hash1")
        sec2 = _section("H2", "d.md", "hash_changed")
        pre = PreprocessResult(sections=[sec1, sec2], symbols=[], file_elements=[])
        doc_map = DocMap(
            mappings=[
                Document(doc_file="d.md", sections=[
                    Section(heading="H1", hash="hash1", files=["a.py"]),
                    Section(heading="H2", hash="hash_old", files=["b.py"]),
                ])
            ]
        )
        result = detect_changes(pre, doc_map)
        assert len(result.unchanged_sections) == 1
        assert result.unchanged_sections[0].heading == "H1"
        assert len(result.changed_sections) == 1
        assert result.changed_sections[0].heading == "H2"

    def test_resolve_from_cache_rebuilds_docmap(self):
        sec1 = _section("H1", "d.md", "h1")
        sec2 = _section("H2", "d.md", "h2")
        cached_index = {
            ("d.md", "H1", 0): Section(heading="H1", hash="h1", files=["a.py"]),
            ("d.md", "H2", 0): Section(heading="H2", hash="h2", files=["b.py", "c.py"]),
        }
        change = ChangeDetection(
            changed_sections=[sec2],
            unchanged_sections=[sec1],
            cached_index=cached_index,
        )
        doc_map, cached, new = resolve_from_cache(change)
        assert cached == 1
        assert new == 1
        all_files = []
        for dm in doc_map.mappings:
            for s in dm.sections:
                all_files.extend(s.files)
        assert "a.py" in all_files
        assert "b.py" in all_files

    def test_merge_unchanged_preserves_cached_mappings(self):
        sec = _section("H1", "d.md", "h1")
        cached_sec = Section(heading="H1", hash="h1", files=["x.py", "y.py"])
        cached_index = {("d.md", "H1", 0): cached_sec}
        change = ChangeDetection(
            changed_sections=[],
            unchanged_sections=[sec],
            cached_index=cached_index,
        )
        retrieval = RetrieveResult(
            heading_to_files={},
            heading_to_rerank_scores={},
            heading_to_classifications={},
        )
        merge_unchanged(retrieval, change)
        key = ("d.md", "H1", 0)
        assert retrieval.heading_to_files[key] == ["x.py", "y.py"]
        assert len(retrieval.heading_to_classifications[key]) == 2
        assert all(c.is_match for c in retrieval.heading_to_classifications[key])
