from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


from speclink.core.config import PipelineConfig
from speclink.core.models import Classification, DocMap
from speclink.core.store import Store
from speclink.retrieval import analyze_repo


def _setup_config(repo_root: Path) -> None:
    speclink = repo_root / ".speclink"
    speclink.mkdir(parents=True, exist_ok=True)
    config = speclink / "config.yaml"
    config.write_text("docs:\n  - docs/api.md\n")


class TestAnalyzeFlow:
    def test_analyze_creates_docmap(self, mini_project: Path):
        _setup_config(mini_project)
        mock_classifier = MagicMock()
        mock_classifier.classify_candidates = AsyncMock(
            return_value=[Classification(target_id="file:src/api.py", is_match=True)]
        )
        mock_classifier.total_input_tokens = 0
        mock_classifier.total_output_tokens = 0

        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value={"src/api.py": 0.9})
        mock_reranker.total_tokens = 0

        config = PipelineConfig(
            llm_model="test-model",
            llm_api_key="test-key",
            rerank_model="test-rerank",
            rerank_api_key="test-rerank-key",
        )
        report = analyze_repo(
            mini_project,
            full=True,
            config=config,
            store=Store(mini_project),
            reranker=mock_reranker,
            classifier=mock_classifier,
        )
        assert report.total_sections > 0
        docmap_path = mini_project / ".speclink" / "docmap.json"
        assert docmap_path.exists()
        dm = DocMap.from_json(docmap_path)
        assert len(dm.mappings) >= 1

    def test_analyze_incremental_skips_unchanged(self, mini_project: Path):
        _setup_config(mini_project)
        mock_classifier = MagicMock()
        mock_classifier.classify_candidates = AsyncMock(
            return_value=[Classification(target_id="file:src/api.py", is_match=True)]
        )
        mock_classifier.total_input_tokens = 0
        mock_classifier.total_output_tokens = 0

        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value={"src/api.py": 0.9})
        mock_reranker.total_tokens = 0

        config = PipelineConfig(
            llm_model="test-model",
            llm_api_key="test-key",
            rerank_model="test-rerank",
            rerank_api_key="test-rerank-key",
        )

        report1 = analyze_repo(
            mini_project,
            full=True,
            config=config,
            store=Store(mini_project),
            reranker=mock_reranker,
            classifier=mock_classifier,
        )
        assert report1.total_sections > 0

        report2 = analyze_repo(
            mini_project,
            full=False,
            config=config,
            store=Store(mini_project),
            reranker=mock_reranker,
            classifier=mock_classifier,
        )
        assert report2.cached_sections > 0

    def test_analyze_empty_repo(self, git_repo: Path):
        _setup_config(git_repo)
        config = PipelineConfig(
            llm_model="test-model",
            llm_api_key="test-key",
            rerank_model="test-rerank",
            rerank_api_key="test-rerank-key",
        )
        mock_classifier = MagicMock()
        mock_classifier.classify_candidates = AsyncMock(return_value=[])
        mock_classifier.total_input_tokens = 0
        mock_classifier.total_output_tokens = 0

        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value={})
        mock_reranker.total_tokens = 0

        report = analyze_repo(
            git_repo,
            full=True,
            config=config,
            store=Store(git_repo),
            reranker=mock_reranker,
            classifier=mock_classifier,
        )
        assert report.total_sections == 0
