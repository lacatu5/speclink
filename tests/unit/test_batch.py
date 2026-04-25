from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import speclink.rewrite.batch as batch_mod
from speclink.core.config import PipelineConfig
from speclink.core.models import DocMap, Document, Section
from speclink.rewrite.batch import (
    build_explicit_instructions,
    collect_batch_code_context,
    collect_batch_diffs,
    extract_current_symbols,
    find_section_mapping,
    process_section_batch,
    remove_file_from_doc_map,
)
from speclink.rewrite.diff import FileChange
from speclink.rewrite.rewriter import SectionRewriter


def _section_index(*entries):
    return {
        (doc_file, heading, 0): Section(heading=heading, file_path=doc_file, hash="h")
        for doc_file, heading in entries
    }


class TestFindSectionMapping:
    def test_finds_matching_section(self):
        idx = _section_index(("docs/a.md", "API Overview"))
        result = find_section_mapping(idx, "docs/a.md", "API Overview")
        assert result is not None
        assert result.heading == "API Overview"

    def test_returns_none_for_missing(self):
        idx = _section_index(("docs/a.md", "API Overview"))
        result = find_section_mapping(idx, "docs/a.md", "Missing Heading")
        assert result is None


class TestRemoveFileFromDocMap:
    def test_removes_file_from_section(self):
        doc_map = DocMap(
            mappings=[
                Document(
                    doc_file="docs/a.md",
                    sections=[
                        Section(
                            heading="API",
                            files=["src/api.py", "src/util.py"],
                        ),
                    ],
                ),
            ],
        )
        remove_file_from_doc_map(doc_map, "docs/a.md", "API", "src/api.py")
        assert doc_map.mappings[0].sections[0].files == ["src/util.py"]

    def test_none_doc_map_does_nothing(self):
        remove_file_from_doc_map(None, "docs/a.md", "API", "src/api.py")


class TestBuildExplicitInstructions:
    def test_deleted_change(self):
        changes = [FileChange(path="src/deleted.py", change_type="deleted")]
        with (
            patch.object(batch_mod, "_DELETED_INSTRUCTION", "Deleted: {path}"),
            patch.object(batch_mod, "_RENAMED_INSTRUCTION", "Renamed: {old_path} -> {new_path}"),
        ):
            result = build_explicit_instructions(changes)
        assert result == "Deleted: src/deleted.py"

    def test_renamed_change(self):
        changes = [
            FileChange(path="src/new.py", change_type="renamed", old_path="src/old.py")
        ]
        with (
            patch.object(batch_mod, "_DELETED_INSTRUCTION", "Deleted: {path}"),
            patch.object(batch_mod, "_RENAMED_INSTRUCTION", "Renamed: {old_path} -> {new_path}"),
        ):
            result = build_explicit_instructions(changes)
        assert result == "Renamed: src/old.py -> src/new.py"


class TestExtractCurrentSymbols:
    def test_unsupported_extension_returns_empty(self, tmp_path: Path):
        fp = tmp_path / "data.xyz"
        fp.write_text("content")
        result = extract_current_symbols(fp, tmp_path)
        assert result == []


@pytest.mark.asyncio
async def test_collect_batch_diffs_with_renamed(git_repo):
    (git_repo / "old.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=git_repo, capture_output=True, check=True)

    subprocess.run(["git", "mv", "old.py", "new.py"], cwd=git_repo, capture_output=True, check=True)
    (git_repo / "new.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "rename"], cwd=git_repo, capture_output=True, check=True)

    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD~1"], cwd=git_repo, capture_output=True, text=True
    ).stdout.strip()

    changes = [FileChange(path="new.py", change_type="renamed", old_path="old.py")]
    result = await collect_batch_diffs(changes, base_sha, "HEAD", git_repo, {})
    assert "new.py" in result


@pytest.mark.asyncio
async def test_collect_batch_diffs_with_modified():
    changes = [FileChange(path="src/api.py", change_type="modified")]
    result = await collect_batch_diffs(changes, "abc", "HEAD", Path("/repo"), {"src/api.py": "some diff"})
    assert "some diff" in result


@pytest.mark.asyncio
async def test_collect_batch_diffs_empty():
    result = await collect_batch_diffs([], "abc", "HEAD", Path("/repo"), {})
    assert result == ""


def test_collect_batch_code_context(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text("def get_user(): pass\n")

    changes = [FileChange(path="src/api.py", change_type="modified")]
    result = collect_batch_code_context(changes, 10, tmp_path)
    assert result is not None
    assert "api.py" in result


def test_collect_batch_code_context_missing_file(tmp_path):
    changes = [FileChange(path="nonexistent.py", change_type="modified")]
    result = collect_batch_code_context(changes, 10, tmp_path)
    assert result is None


@pytest.mark.asyncio
async def test_process_section_batch_rewrite(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    doc_file = docs / "api.md"
    doc_file.write_text("# API\n\nSome content here.\n")

    section_index = {
        ("docs/api.md", "API", 0): Section(heading="API", file_path="docs/api.md", files=["src/api.py"], hash="h"),
    }
    section_cache = {("docs/api.md", "API"): "Some content here."}
    diff_cache = {"src/api.py": "some diff"}

    config = PipelineConfig(llm_model="test", llm_api_key="test", rerank_model="test", rerank_api_key="test")
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        rewriter = SectionRewriter(config=config)

    rewriter.llm_call = AsyncMock(return_value=MagicMock(new_text="Updated content here"))

    changes = [FileChange(path="src/api.py", change_type="modified")]

    results = await process_section_batch(
        ("docs/api.md", "API"),
        changes,
        "abc",
        "HEAD",
        section_index,
        diff_cache,
        section_cache,
        rewriter,
        10,
        tmp_path,
    )

    assert len(results) == 1
    assert results[0].action == "rewrite"
    assert "Updated content here" in doc_file.read_text()
