import os

os.environ.setdefault("LITELLM_LOG", "ERROR")

import asyncio
from typing import Any

import instructor
import litellm
import structlog
from litellm import exceptions as litexceptions

from .config import PipelineConfig

litellm.suppress_debug_info = True

log = structlog.get_logger()

RETRYABLE_EXCEPTIONS = (
    litexceptions.APIConnectionError,
    litexceptions.RateLimitError,
    litexceptions.ServiceUnavailableError,
    litexceptions.InternalServerError,
    litexceptions.BadGatewayError,
)


class LLMClient:
    def __init__(
        self,
        model: str | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.model = model.strip() if model else self.config.llm_model
        self.max_retries = (
            max_retries if max_retries is not None else self.config.max_retries
        )
        self.timeout = timeout if timeout is not None else self.config.timeout
        self.temperature = self.config.temperature
        self.drop_params = self.config.drop_params
        self.api_key = self.config.llm_api_key
        self.client = instructor.from_litellm(
            litellm.acompletion,
            mode=instructor.Mode.JSON,
        )
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def llm_call(
        self,
        response_model: type,
        messages: list[dict[str, str]],
        *,
        max_retries: int | None = None,
        timeout: int | None = None,
    ) -> Any:
        attempts = max_retries if max_retries is not None else self.max_retries
        _timeout = timeout if timeout is not None else self.timeout
        for attempt in range(attempts):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    drop_params=self.drop_params,
                    response_model=response_model,
                    messages=messages,
                    timeout=_timeout,
                    api_key=self.api_key,
                )
                raw = (
                    response._raw_response
                    if hasattr(response, "_raw_response")
                    else response
                )
                usage = getattr(raw, "usage", None)
                if usage:
                    self.total_input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                    self.total_output_tokens += (
                        getattr(usage, "completion_tokens", 0) or 0
                    )
                return response
            except RETRYABLE_EXCEPTIONS as e:
                if attempt == attempts - 1:
                    raise
                wait = min(
                    2.0 * (2**attempt),
                    10.0,
                )
                log.warning(
                    "llm_retry",
                    attempt=attempt + 1,
                    error_type=type(e).__name__,
                    wait=wait,
                )
                await asyncio.sleep(wait)
