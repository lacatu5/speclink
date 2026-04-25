import structlog
from pydantic import BaseModel

from speclink._prompts import load_prompt
from speclink.core.config import PipelineConfig
from speclink.core.llm import LLMClient

log = structlog.get_logger()



_REWRITER_PROMPTS = load_prompt("rewriter")
SYSTEM_PROMPT = _REWRITER_PROMPTS["system"]
USER_PROMPT_TEMPLATE = _REWRITER_PROMPTS["user"]


class _FullSectionRewrite(BaseModel):
    new_text: str


class SectionRewriter(LLMClient):
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

    def build_prompt(
        self,
        heading: str,
        current_text: str,
        diff_context: str | None = None,
        code_context: str | None = None,
        explicit_changes: str | None = None,
    ) -> str:
        parts = []
        if diff_context:
            parts.append(f"\n\n### Code Changes (Git Diff)\n{diff_context}")
        if code_context:
            parts.append(f"\n\n### Current Code\n{code_context}")
        context_section = "".join(parts)

        explicit_section = (
            f"\n\n### Required Changes\n{explicit_changes}" if explicit_changes else ""
        )

        return USER_PROMPT_TEMPLATE.format(
            heading=heading,
            current_text=current_text,
            context_section=context_section,
            explicit_section=explicit_section,
        )

    async def rewrite_section(
        self,
        heading: str,
        current_text: str,
        diff_context: str | None = None,
        code_context: str | None = None,
        explicit_changes: str | None = None,
    ) -> str:
        response = await self.llm_call(
            _FullSectionRewrite,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self.build_prompt(
                        heading,
                        current_text,
                        diff_context=diff_context,
                        code_context=code_context,
                        explicit_changes=explicit_changes,
                    ),
                },
            ],
        )

        if not response.new_text:
            return current_text

        new_text = response.new_text.strip()

        first_line = new_text.splitlines()[0].strip().lstrip("#").strip()
        if first_line == heading:
            new_text = new_text.split("\n", 1)[1].strip() if "\n" in new_text else ""

        norm_new = "\n".join(
            line.rstrip() for line in new_text.splitlines() if line.strip()
        )
        norm_orig = "\n".join(
            line.rstrip() for line in current_text.splitlines() if line.strip()
        )
        if norm_new == norm_orig:
            return current_text

        if len(new_text) > len(current_text) * 1.5:
            log.warning(
                "rewrite_rejected",
                reason="new text much longer than original",
                orig_len=len(current_text),
                new_len=len(new_text),
            )
            return current_text

        return new_text
