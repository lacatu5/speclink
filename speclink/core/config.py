from pathlib import Path
from typing import Tuple, Type

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
import yaml


def _resolve_yaml_path() -> str:
    candidate = Path.cwd() / ".speclink" / "config.yaml"
    if candidate.exists():
        data = yaml.safe_load(candidate.read_text())
        if isinstance(data, dict):
            return str(candidate)
    fallback = Path.cwd() / "config.yaml"
    if fallback.exists():
        return str(fallback)
    return ""


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config.yaml",
        yaml_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        from pydantic_settings import YamlConfigSettingsSource

        yaml_source = YamlConfigSettingsSource(
            settings_cls,
            yaml_file=_resolve_yaml_path(),
        )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_source,
            file_secret_settings,
        )

    llm_model: str = Field(default="", validation_alias="LLM_MODEL")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    rerank_model: str = Field(default="", validation_alias="RERANK_MODEL")
    rerank_api_key: str = Field(default="", validation_alias="RERANK_API_KEY")

    temperature: float = 0
    drop_params: bool = True
    max_retries: int = 3
    timeout: int = 60
    max_concurrent: int = 50

    max_context_items: int = Field(
        default=30,
        validation_alias="MAX_CONTEXT_ITEMS",
    )

    max_signatures: int = 100
    max_variables: int = 30
    rerank_floor: float = 0.5
    rerank_gap: float = 0.15
    rerank_batch_size: int = 1000

    max_paragraph_length: int = 2000
    max_paragraph_tokens: int = 8000

