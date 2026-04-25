from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from speclink.retrieval.reranker import Reranker


def test_reranker_init(mock_config):
    r = Reranker(config=mock_config)
    assert r.model == mock_config.rerank_model
    assert r.api_key == mock_config.rerank_api_key
    assert r.total_tokens == 0


@pytest.mark.asyncio
async def test_rerank_empty_candidates(mock_config, sample_section):
    r = Reranker(config=mock_config)
    result = await r.rerank(sample_section, [])
    assert result == {}


@pytest.mark.asyncio
async def test_rerank_returns_scores(mock_config, sample_section):
    r = Reranker(config=mock_config)
    mock_response = MagicMock()
    mock_response.results = [
        {"index": 0, "relevance_score": 0.9},
        {"index": 1, "relevance_score": 0.7},
    ]
    mock_response.meta = {"tokens": {"input_tokens": 100, "output_tokens": 50}}
    with patch(
        "speclink.retrieval.reranker.litellm.arerank",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await r.rerank(sample_section, ["src/api.py", "src/utils.py"])
    assert result == {"src/api.py": 0.9, "src/utils.py": 0.7}
    assert r.total_tokens == 150


@pytest.mark.asyncio
async def test_rerank_handles_exception(mock_config, sample_section):
    from litellm.exceptions import APIConnectionError
    r = Reranker(config=mock_config)
    with patch(
        "speclink.retrieval.reranker.litellm.arerank",
        new_callable=AsyncMock,
        side_effect=APIConnectionError(message="fail", model="m", llm_provider="p"),
    ):
        result = await r.rerank(sample_section, ["src/api.py"])
    assert result == {}
