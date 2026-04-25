from pathlib import Path

import litellm
import structlog

from speclink.core.config import PipelineConfig
from speclink.core.llm import RETRYABLE_EXCEPTIONS
from speclink.core.models import Section

log = structlog.get_logger()


class Reranker:
    def __init__(
        self,
        config: PipelineConfig,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.config = config
        self.model = model or config.rerank_model
        self.api_key = api_key or config.rerank_api_key
        self.total_tokens = 0

    async def rerank(
        self,
        section: Section,
        candidate_files: list[str],
        sig_map: dict[str, list[str]] | None = None,
        variables_map: dict[str, list[str]] | None = None,
    ) -> dict[str, float]:
        if not candidate_files:
            return {}

        fname = Path(section.file_path).name
        query = f"Search for code implementing: {section.heading} (in {fname})"
        if section.content:
            query += f"\n\nContext:\n{section.content}"

        documents = []
        for fid in candidate_files:
            parts = [f"File: {fid}"]

            sigs = sig_map.get(fid, []) if sig_map else []
            if sigs:
                parts.append(
                    "Signatures:\n"
                    + "\n".join(f"- {s}" for s in sigs[: self.config.max_signatures])
                )

            variables = variables_map.get(fid, []) if variables_map else []
            if variables:
                parts.append(
                    "Variables:\n"
                    + "\n".join(
                        f"- {v}" for v in variables[: self.config.max_variables]
                    )
                )

            documents.append("\n\n".join(parts))

        batch_size = self.config.rerank_batch_size
        all_scores: dict[str, float] = {}

        for start in range(0, len(documents), batch_size):
            batch_docs = documents[start : start + batch_size]
            batch_ids = candidate_files[start : start + batch_size]

            try:
                response = await litellm.arerank(
                    model=self.model,
                    query=query,
                    documents=batch_docs,
                    top_n=len(batch_ids),
                    api_key=self.api_key,
                )
                meta = getattr(response, "meta", None)
                if meta:
                    tokens = meta.get("tokens") if isinstance(meta, dict) else getattr(meta, "tokens", None)
                    if tokens:
                        self.total_tokens += (tokens.get("input_tokens", 0) or 0) + (tokens.get("output_tokens", 0) or 0)
                for r in response.results:
                    all_scores[batch_ids[r["index"]]] = r["relevance_score"]
            except RETRYABLE_EXCEPTIONS as e:
                log.error(
                    "reranking_failed",
                    model=self.model,
                    batch_start=start,
                    batch_size=len(batch_docs),
                    error=str(e),
                    error_type=type(e).__name__,
                )

        return all_scores
