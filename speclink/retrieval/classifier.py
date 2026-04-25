import asyncio
from typing import Literal

import structlog
from pydantic import BaseModel

from speclink._prompts import load_prompt
from speclink.core.config import PipelineConfig
from speclink.core.llm import LLMClient
from speclink.core.models import Classification, CodeElement, Section

_CLASSIFICATION_RAW = load_prompt("classification")
CLASSIFICATION_PROMPT = _CLASSIFICATION_RAW["user"]
SYSTEM_PROMPT = _CLASSIFICATION_RAW["system"]

log = structlog.get_logger()


class _ClassifierResponse(BaseModel):
    decision: Literal["TRUE", "FALSE"]
    reasoning: str


class ReasoningClassifier(LLMClient):
    def __init__(
        self,
        config: PipelineConfig,
        model: str | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
    ) -> None:
        super().__init__(
            model=model, max_retries=max_retries, timeout=timeout, config=config
        )
        self.max_signatures = self.config.max_signatures

    def build_prompt(
        self,
        source: Section,
        target: CodeElement,
        doc_filename: str = "",
        signatures: list[str] | None = None,
        variables: list[str] | None = None,
    ) -> str:
        source_content = f"{source.heading}\n\n{source.content}"
        target_parts = [f"File: {target.file_path}"]
        if signatures:
            sigs = signatures[: self.max_signatures]
            sig_text = "\n".join(f"  {s}" for s in sigs)
            target_parts.append(f"Signatures:\n{sig_text}")
        if variables:
            var_text = "\n".join(f"  {v}" for v in variables[: self.config.max_variables])
            target_parts.append(f"Variables:\n{var_text}")
        target_content = "\n".join(target_parts)
        doc_context = f" from {doc_filename}" if doc_filename else ""
        return CLASSIFICATION_PROMPT.format(
            source_type=f"Documentation{doc_context}",
            source_content=source_content,
            target_type="Code",
            target_content=target_content,
        )

    async def classify_pair(
        self,
        source: Section,
        target: CodeElement,
        doc_filename: str = "",
        signatures: list[str] | None = None,
        variables: list[str] | None = None,
    ) -> Classification:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self.build_prompt(
                    source, target, doc_filename=doc_filename, signatures=signatures,
                    variables=variables,
                ),
            },
        ]
        response: _ClassifierResponse = await self.llm_call(
            _ClassifierResponse,
            messages,
            max_retries=3,
        )
        return Classification(target_id=target.id, is_match=response.decision == "TRUE")

    async def classify_candidates(
        self,
        source: Section,
        candidates: list[CodeElement],
        doc_filename: str = "",
        max_concurrent: int | None = None,
        sig_map: dict[str, list[str]] | None = None,
        variables_map: dict[str, list[str]] | None = None,
    ) -> list[Classification]:
        max_concurrent = max_concurrent or self.config.max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_pair(candidate: CodeElement) -> Classification:
            async with semaphore:
                try:
                    sigs = sig_map.get(candidate.file_path) if sig_map else None
                    vars_ = variables_map.get(candidate.file_path) if variables_map else None
                    return await self.classify_pair(
                        source, candidate, doc_filename=doc_filename, signatures=sigs,
                        variables=vars_,
                    )
                except (RuntimeError, ValueError) as exc:
                    log.warning(
                        "pair_classify_failed", target=candidate.id, error=str(exc)
                    )
                    return Classification(target_id=candidate.id, is_match=False)

        return list(await asyncio.gather(*(limited_pair(c) for c in candidates)))
