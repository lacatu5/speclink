from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from speclink.core.config import PipelineConfig
from speclink.core.store import Store
from speclink.rewrite import sync_repo
from tests.conftest import git_commit, write_doc_map


def _git_commit(repo: Path, msg: str = "commit") -> str:
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", msg, "--allow-empty"], cwd=repo, capture_output=True, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()


class TestSyncFlow:
    def test_sync_updates_docmap(self, mini_project: Path):
        mappings = [
            {
                "doc_file": "docs/api.md",
                "sections": [
                    {"heading": "API Overview", "files": ["src/api.py"], "hash": "old_hash"},
                ],
            }
        ]
        base_sha = _git_commit(mini_project, "base")
        write_doc_map(mini_project, base_sha, mappings)

        (mini_project / "src" / "api.py").write_text(
            'def get_user(uid: str) -> dict:\n    return {"id": uid}\n\ndef delete_user(uid: str) -> dict:\n    return {"deleted": uid}\n'
        )
        _git_commit(mini_project, "update api")

        mock_result = MagicMock()
        mock_result.new_text = "Updated API overview with new functions."

        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_section = AsyncMock(return_value=mock_result)
        mock_rewriter.total_input_tokens = 0
        mock_rewriter.total_output_tokens = 0

        config = PipelineConfig(
            llm_model="test-model",
            llm_api_key="test-key",
            rerank_model="test-rerank",
            rerank_api_key="test-rerank-key",
        )
        report = sync_repo(
            mini_project,
            config=config,
            store=Store(mini_project),
            rewriter=mock_rewriter,
        )
        assert len(report.actions) >= 1

    def test_sync_no_changes(self, mini_project: Path):
        mappings = [
            {
                "doc_file": "docs/api.md",
                "sections": [
                    {"heading": "API Overview", "files": ["src/api.py"], "hash": "h1"},
                ],
            }
        ]
        base_sha = _git_commit(mini_project, "base")
        write_doc_map(mini_project, base_sha, mappings)

        config = PipelineConfig(
            llm_model="test-model",
            llm_api_key="test-key",
            rerank_model="test-rerank",
            rerank_api_key="test-rerank-key",
        )
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_section = AsyncMock(return_value=MagicMock(new_text=""))
        mock_rewriter.total_input_tokens = 0
        mock_rewriter.total_output_tokens = 0

        report = sync_repo(
            mini_project,
            config=config,
            store=Store(mini_project),
            rewriter=mock_rewriter,
        )
        assert report.total_errors == 0

    def test_sync_deleted_file(self, mini_project: Path):
        (mini_project / "src" / "tasks.py").write_text("def run_task(): pass\n")
        base_sha = git_commit(mini_project, "add tasks")

        mappings = [
            {
                "doc_file": "docs/api.md",
                "sections": [
                    {"heading": "API Overview", "files": ["src/api.py", "src/tasks.py"], "hash": "h1"},
                ],
            }
        ]
        write_doc_map(mini_project, base_sha, mappings)

        (mini_project / "src" / "tasks.py").unlink()
        _git_commit(mini_project, "remove tasks")

        config = PipelineConfig(
            llm_model="test-model",
            llm_api_key="test-key",
            rerank_model="test-rerank",
            rerank_api_key="test-rerank-key",
        )
        mock_result = MagicMock()
        mock_result.new_text = "Updated content without tasks."
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_section = AsyncMock(return_value=mock_result)
        mock_rewriter.total_input_tokens = 0
        mock_rewriter.total_output_tokens = 0

        report = sync_repo(
            mini_project,
            config=config,
            store=Store(mini_project),
            rewriter=mock_rewriter,
        )
        assert len(report.actions) >= 1
