from __future__ import annotations

from speclink.core.models import DocMap, Document, Section
from speclink.rewrite.diff import FileChange, find_stale_sections
from speclink.rewrite.stages import _update_memory_path, build_section_groups


class TestRewritePipeline:
    def test_find_stale_sections_with_real_docmap(self, tmp_path):
        from tests.conftest import write_doc_map

        mappings = [
            {
                "doc_file": "docs/api.md",
                "sections": [
                    {"heading": "API", "files": ["src/api.py", "src/util.py"]},
                    {"heading": "Models", "files": ["src/models.py"]},
                ],
            }
        ]
        write_doc_map(tmp_path, "sha1", mappings)
        doc_map = DocMap.from_json(tmp_path / ".speclink" / "docmap.json")
        stale = find_stale_sections(doc_map, ["src/api.py"])
        assert len(stale) == 1
        assert stale[0].heading == "API"
        assert "src/api.py" in stale[0].changed_files

    def test_build_section_groups_groups_correctly(self):
        doc_map = DocMap(
            mappings=[
                Document(doc_file="d.md", sections=[
                    Section(heading="H1", files=["a.py", "b.py"]),
                    Section(heading="H2", files=["c.py"]),
                ])
            ]
        )
        changes = [
            FileChange(path="a.py", change_type="modified"),
            FileChange(path="c.py", change_type="modified"),
        ]
        groups = build_section_groups(doc_map, changes)
        assert ("d.md", "H1") in groups
        assert ("d.md", "H2") in groups
        assert len(groups[("d.md", "H1")]) == 1
        assert groups[("d.md", "H1")][0].path == "a.py"

    def test_update_memory_path_renames_files(self):
        doc_map = DocMap(
            mappings=[
                Document(doc_file="d.md", sections=[
                    Section(heading="H1", files=["old.py", "other.py"]),
                ])
            ]
        )
        _update_memory_path(doc_map, "old.py", "new.py")
        files = doc_map.mappings[0].sections[0].files
        assert "new.py" in files
        assert "old.py" not in files
        assert "other.py" in files
