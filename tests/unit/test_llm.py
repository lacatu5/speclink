from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import APIConnectionError, RateLimitError

from speclink.core.llm import LLMClient


def _patch_instructor():
    return patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock())


def test_llm_client_sets_model_from_config(mock_config):
    with _patch_instructor():
        client = LLMClient(config=mock_config)
    assert client.model == mock_config.llm_model


def test_llm_client_explicit_model_overrides_config(mock_config):
    with _patch_instructor():
        client = LLMClient(model="custom-model", config=mock_config)
    assert client.model == "custom-model"


def test_llm_client_tokens_start_at_zero(mock_config):
    with _patch_instructor():
        client = LLMClient(config=mock_config)
    assert client.total_input_tokens == 0
    assert client.total_output_tokens == 0


def test_llm_client_uses_config_defaults(mock_config):
    with _patch_instructor():
        client = LLMClient(config=mock_config)
    assert client.max_retries == mock_config.max_retries
    assert client.timeout == mock_config.timeout


@pytest.mark.asyncio
async def test_llm_call_success(mock_config):
    mock_response = MagicMock()
    mock_raw = MagicMock()
    mock_raw.usage = MagicMock()
    mock_raw.usage.prompt_tokens = 10
    mock_raw.usage.completion_tokens = 5
    mock_response._raw_response = mock_raw
    with _patch_instructor():
        client = LLMClient(config=mock_config)
        client.client = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await client.llm_call(MagicMock, [{"role": "user", "content": "hi"}])
    assert result == mock_response
    assert client.total_input_tokens == 10
    assert client.total_output_tokens == 5


@pytest.mark.asyncio
async def test_llm_call_retries_on_retryable_error(mock_config):
    mock_response = MagicMock()
    mock_response._raw_response = MagicMock()
    mock_create = AsyncMock(side_effect=[RateLimitError("rate limited", model="test", llm_provider="test"), mock_response])

    with _patch_instructor():
        client = LLMClient(config=mock_config)
        client.client = MagicMock()
        client.client.chat.completions.create = mock_create
        with patch("speclink.core.llm.asyncio.sleep", new_callable=AsyncMock):
            result = await client.llm_call(MagicMock, [{"role": "user", "content": "hi"}])
    assert result == mock_response


@pytest.mark.asyncio
async def test_llm_call_raises_after_max_retries(mock_config):
    with _patch_instructor():
        client = LLMClient(config=mock_config, max_retries=1)
        client.client = MagicMock()
        client.client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError("conn error", model="test", llm_provider="test")
        )
        with pytest.raises(APIConnectionError):
            await client.llm_call(MagicMock, [{"role": "user", "content": "hi"}])
