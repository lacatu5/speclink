from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from speclink.core.llm import LLMClient
from speclink.core.models import Classification, CodeElement
from speclink.retrieval.classifier import ReasoningClassifier


def test_classifier_inherits_llm_client(mock_config):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)
    assert isinstance(clf, LLMClient)


def test_build_prompt_includes_source_heading_and_content(mock_config, sample_section, sample_code_element):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)
    result = clf.build_prompt(sample_section, sample_code_element)
    assert sample_section.heading in result
    assert sample_section.content in result


def test_build_prompt_includes_target_file_path(mock_config, sample_section, sample_code_element):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)
    result = clf.build_prompt(sample_section, sample_code_element)
    assert sample_code_element.file_path in result


def test_build_prompt_includes_signatures(mock_config, sample_section, sample_code_element):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)
    sigs = ["def get_user(user_id: int) -> User", "def delete_user(id: int) -> None"]
    result = clf.build_prompt(sample_section, sample_code_element, signatures=sigs)
    assert "def get_user" in result
    assert "def delete_user" in result


@pytest.mark.asyncio
async def test_classify_pair_returns_classification(mock_config, sample_section, sample_code_element):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)

    mock_response = MagicMock()
    mock_response.decision = "TRUE"
    mock_response.reasoning = "match"

    clf.llm_call = AsyncMock(return_value=mock_response)
    result = await clf.classify_pair(sample_section, sample_code_element)
    assert isinstance(result, Classification)
    assert result.is_match is True


@pytest.mark.asyncio
async def test_classify_candidates_handles_errors(mock_config, sample_section):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)

    clf.llm_call = AsyncMock(side_effect=ValueError("boom"))
    candidates = [
        CodeElement(id="a::f", name="f", signature="def f()", code="pass", file_path="a.py")
    ]
    results = await clf.classify_candidates(sample_section, candidates)
    assert len(results) == 1
    assert results[0].is_match is False


def test_build_prompt_includes_variables(mock_config, sample_section, sample_code_element):
    with patch("speclink.core.llm.instructor.from_litellm", return_value=MagicMock()):
        clf = ReasoningClassifier(config=mock_config)
    result = clf.build_prompt(
        sample_section, sample_code_element,
        variables=["API_KEY = os.getenv('KEY')"],
    )
    assert "API_KEY" in result
