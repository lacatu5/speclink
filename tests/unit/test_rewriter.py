from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from speclink.core.llm import LLMClient
from speclink.rewrite.rewriter import SectionRewriter


def _make_rewriter(mock_config):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        return SectionRewriter(config=mock_config)


def test_rewriter_inherits_llm_client(mock_config):
    rw = _make_rewriter(mock_config)
    assert isinstance(rw, LLMClient)


def test_build_prompt_includes_heading_and_current_text(mock_config):
    rw = _make_rewriter(mock_config)
    result = rw.build_prompt(heading="API Overview", current_text="Some docs here")
    assert "API Overview" in result
    assert "Some docs here" in result


def test_build_prompt_includes_diff_context(mock_config):
    rw = _make_rewriter(mock_config)
    result = rw.build_prompt(
        heading="API Overview",
        current_text="text",
        diff_context="--- a/src/api.py\n+++ b/src/api.py",
    )
    assert "Code Changes (Git Diff)" in result
    assert "src/api.py" in result


def test_build_prompt_includes_code_context(mock_config):
    rw = _make_rewriter(mock_config)
    result = rw.build_prompt(
        heading="API Overview",
        current_text="text",
        code_context="def get_user(): pass",
    )
    assert "Current Code" in result
    assert "def get_user" in result


def test_build_prompt_includes_explicit_changes(mock_config):
    rw = _make_rewriter(mock_config)
    result = rw.build_prompt(
        heading="API Overview",
        current_text="text",
        explicit_changes="Update endpoint to v2",
    )
    assert "Required Changes" in result
    assert "Update endpoint to v2" in result


@pytest.mark.asyncio
async def test_rewrite_section_returns_new_text(mock_config):
    rw = _make_rewriter(mock_config)
    mock_response = MagicMock()
    mock_response.new_text = "updated text"
    rw.llm_call = AsyncMock(return_value=mock_response)
    result = await rw.rewrite_section("API Overview", "old text here and more padding")
    assert result == "updated text"


@pytest.mark.asyncio
async def test_rewrite_section_returns_original_when_empty(mock_config):
    rw = _make_rewriter(mock_config)
    mock_response = MagicMock()
    mock_response.new_text = ""
    rw.llm_call = AsyncMock(return_value=mock_response)
    result = await rw.rewrite_section("API Overview", "original text")
    assert result == "original text"


@pytest.mark.asyncio
async def test_rewrite_section_strips_heading_from_response(mock_config):
    rw = _make_rewriter(mock_config)
    mock_response = MagicMock()
    mock_response.new_text = "API Overview\nupdated text"
    rw.llm_call = AsyncMock(return_value=mock_response)
    result = await rw.rewrite_section("API Overview", "old text here and more padding")
    assert result == "updated text"


@pytest.mark.asyncio
async def test_rewrite_section_rejects_oversized_rewrite(mock_config):
    rw = _make_rewriter(mock_config)
    mock_response = MagicMock()
    mock_response.new_text = "x" * 200
    rw.llm_call = AsyncMock(return_value=mock_response)
    result = await rw.rewrite_section("API Overview", "short")
    assert result == "short"


@pytest.mark.asyncio
async def test_rewrite_section_returns_original_when_identical(mock_config):
    rw = _make_rewriter(mock_config)
    mock_response = MagicMock()
    mock_response.new_text = "same content"
    rw.llm_call = AsyncMock(return_value=mock_response)
    result = await rw.rewrite_section("Heading", "same content")
    assert result == "same content"
