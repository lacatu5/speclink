from __future__ import annotations


from speclink.core.config import PipelineConfig


def test_default_values():
    cfg = PipelineConfig()
    assert cfg.temperature == 0
    assert cfg.max_retries == 3
    assert cfg.timeout == 60
    assert cfg.max_concurrent == 50
    assert cfg.max_signatures == 100
    assert cfg.max_variables == 30
    assert cfg.max_paragraph_length == 2000
    assert cfg.max_paragraph_tokens == 8000


def test_custom_values():
    cfg = PipelineConfig(temperature=0.7, max_retries=5, timeout=120)
    assert cfg.temperature == 0.7
    assert cfg.max_retries == 5
    assert cfg.timeout == 120


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    cfg = PipelineConfig()
    assert cfg.llm_model == "gpt-4o"


def test_rerank_defaults():
    cfg = PipelineConfig()
    assert cfg.rerank_floor == 0.5
    assert cfg.rerank_gap == 0.15


def test_drop_params_default():
    cfg = PipelineConfig()
    assert cfg.drop_params is True
