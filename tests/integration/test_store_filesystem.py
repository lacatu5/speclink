from __future__ import annotations

import json
from pathlib import Path

from speclink.core.models import DocMap, Document, Section
from speclink.core.store import Store


class TestStoreFilesystem:
    def test_persist_doc_map_creates_file(self, tmp_path: Path, sample_doc_map: DocMap):
        store = Store(tmp_path)
        target = tmp_path / ".speclink" / "docmap.json"
        store.persist_doc_map(sample_doc_map, target)
        assert target.exists()
        data = json.loads(target.read_text())
        assert data["codebase_sha"] == "abc123"

    def test_persist_doc_map_updates_codebase_sha(self, tmp_path: Path, sample_doc_map: DocMap):
        store = Store(tmp_path)
        target = tmp_path / ".speclink" / "docmap.json"
        store.persist_doc_map(sample_doc_map, target, codebase_sha="newsha")
        data = json.loads(target.read_text())
        assert data["codebase_sha"] == "newsha"
        assert sample_doc_map.codebase_sha == "newsha"

    def test_save_eval_creates_file(self, tmp_path: Path):
        store = Store(tmp_path)
        entries = [{"doc_file": "d.md", "heading": "H", "file": "a.py", "score": 0.9}]
        store.save_eval("reranker", "model-x", entries, eval_mode=True)
        run_dir = tmp_path / ".speclink" / "runs" / "reranker"
        files = list(run_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["model"] == "model-x"
        assert len(data["entries"]) == 1

    def test_persist_doc_map_sorts_output(self, tmp_path: Path):
        store = Store(tmp_path)
        dm = DocMap(
            mappings=[
                Document(doc_file="z.md", sections=[Section(heading="B", files=["b.py", "a.py"])]),
                Document(doc_file="a.md", sections=[Section(heading="A", files=[])]),
            ]
        )
        target = tmp_path / ".speclink" / "docmap.json"
        store.persist_doc_map(dm, target)
        data = json.loads(target.read_text())
        assert data["mappings"][0]["doc_file"] == "a.md"
        assert data["mappings"][1]["sections"][0]["files"] == ["a.py", "b.py"]
