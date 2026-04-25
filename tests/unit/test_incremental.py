from __future__ import annotations

from speclink.core.models import DocMap, Document, Section
from speclink.retrieval.incremental import (
    ChangeDetection,
    detect_changes,
    merge_unchanged,
    resolve_from_cache,
)
from speclink.retrieval.stages import PreprocessResult, RetrieveResult


def _make_section(heading: str, file_path: str, hash: str, chunk_index: int = 0) -> Section:
    return Section(
        heading=heading,
        content="content",
        file_path=file_path,
        hash=hash,
        chunk_index=chunk_index,
    )


def _make_doc_map_with_hash(heading: str, file_path: str, hash: str, doc_file: str = "docs/api.md") -> DocMap:
    return DocMap(
        mappings=[
            Document(
                doc_file=doc_file,
                sections=[
                    Section(heading=heading, hash=hash, files=["src/api.py"], file_path=doc_file),
                ],
            )
        ]
    )


class TestDetectChanges:
    def test_no_existing_doc_map_all_changed(self):
        sections = [_make_section("H1", "docs/a.md", "h1")]
        pre = PreprocessResult(sections=sections, symbols=[], file_elements=[])
        result = detect_changes(pre, None)
        assert len(result.changed_sections) == 1
        assert len(result.unchanged_sections) == 0

    def test_matching_hash_unchanged(self):
        sec = _make_section("H1", "docs/api.md", "hash1")
        pre = PreprocessResult(sections=[sec], symbols=[], file_elements=[])
        doc_map = _make_doc_map_with_hash("H1", "docs/api.md", "hash1")
        result = detect_changes(pre, doc_map)
        assert len(result.unchanged_sections) == 1
        assert len(result.changed_sections) == 0

    def test_mismatched_hash_changed(self):
        sec = _make_section("H1", "docs/api.md", "new_hash")
        pre = PreprocessResult(sections=[sec], symbols=[], file_elements=[])
        doc_map = _make_doc_map_with_hash("H1", "docs/api.md", "old_hash")
        result = detect_changes(pre, doc_map)
        assert len(result.changed_sections) == 1
        assert len(result.unchanged_sections) == 0

    def test_skip_cache_all_changed(self):
        sec = _make_section("H1", "docs/api.md", "hash1")
        pre = PreprocessResult(sections=[sec], symbols=[], file_elements=[])
        doc_map = _make_doc_map_with_hash("H1", "docs/api.md", "hash1")
        result = detect_changes(pre, doc_map, skip_cache=True)
        assert len(result.changed_sections) == 1
        assert len(result.unchanged_sections) == 0


class TestResolveFromCache:
    def test_builds_doc_map_with_cached_files(self):
        sec = _make_section("H1", "docs/a.md", "hash1")
        cached_index = {
            ("docs/a.md", "H1", 0): Section(
                heading="H1", hash="hash1", files=["src/api.py", "src/util.py"]
            )
        }
        change = ChangeDetection(
            changed_sections=[],
            unchanged_sections=[sec],
            cached_index=cached_index,
        )
        doc_map, unchanged, changed = resolve_from_cache(change)
        assert unchanged == 1
        assert changed == 0
        assert len(doc_map.mappings) == 1
        files = doc_map.mappings[0].sections[0].files
        assert "src/api.py" in files
        assert "src/util.py" in files


class TestMergeUnchanged:
    def test_populates_retrieval_from_cache(self):
        sec = _make_section("H1", "docs/a.md", "hash1")
        cached_sec = Section(
            heading="H1", hash="hash1", files=["src/api.py", "src/util.py"]
        )
        cached_index = {("docs/a.md", "H1", 0): cached_sec}
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
        key = ("docs/a.md", "H1", 0)
        assert retrieval.heading_to_files[key] == ["src/api.py", "src/util.py"]
        assert retrieval.heading_to_rerank_scores[key] == {}
        assert len(retrieval.heading_to_classifications[key]) == 2
        assert all(c.is_match for c in retrieval.heading_to_classifications[key])
