"""Provider-neutral chat-completion client using OpenAI-compatible APIs."""

import time
from dataclasses import dataclass

from openai import APIConnectionError, APIError, APIStatusError, OpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.observability.tracing import remote_observation


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


# USD per one million tokens. Unknown models intentionally report no estimate.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-3.1-flash-lite": (0.25, 1.50),
}


class LLMClient:
    """LLM client with bounded retry, timeout, usage, cost, and tracing."""

    def __init__(
        self,
        model: str | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        settings = get_settings()
        provider = settings.llm_provider.lower()
        if provider not in {"auto", "gemini", "openai"}:
            raise AgentExecutionError("LLM_PROVIDER must be auto, gemini, or openai")
        use_gemini = provider == "gemini" or (provider == "auto" and bool(settings.gemini_api_key))
        api_key = settings.gemini_api_key if use_gemini else settings.openai_api_key
        base_url = settings.gemini_base_url if use_gemini else settings.openai_base_url
        configured_model = settings.gemini_model if use_gemini else settings.openai_model
        if not api_key:
            selected = "GEMINI_API_KEY" if use_gemini else "OPENAI_API_KEY"
            raise AgentExecutionError(f"{selected} is not configured")
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )
        self._model = model or configured_model
        self._provider = "gemini" if use_gemini else "openai"
        self._max_retries = max_retries

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        observation_name: str = "generate-completion",
    ) -> LLMResponse:
        """Call the configured LLM with bounded retries and generation tracing."""
        last_error: Exception | None = None
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for attempt in range(1, self._max_retries + 1):
            with remote_observation(
                name=observation_name,
                as_type="generation",
                input=messages,
                metadata={"provider": self._provider, "attempt": attempt},
                model=self._model,
                model_parameters={"temperature": 0.3},
            ) as generation:
                try:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        temperature=0.3,
                    )
                    choice = response.choices[0]
                    usage = response.usage
                    input_tokens = usage.prompt_tokens if usage else None
                    output_tokens = usage.completion_tokens if usage else None

                    input_cost: float | None = None
                    output_cost: float | None = None
                    pricing = _MODEL_PRICING.get(self._model)
                    if pricing and input_tokens is not None and output_tokens is not None:
                        input_cost = input_tokens / 1_000_000 * pricing[0]
                        output_cost = output_tokens / 1_000_000 * pricing[1]
                    cost = (
                        input_cost + output_cost
                        if input_cost is not None and output_cost is not None
                        else None
                    )
                    content = choice.message.content or ""
                    if generation is not None:
                        generation.update(
                            output={"role": "assistant", "content": content},
                            usage_details={
                                "input": input_tokens or 0,
                                "output": output_tokens or 0,
                            },
                            cost_details={
                                "input": input_cost or 0.0,
                                "output": output_cost or 0.0,
                            }
                            if cost is not None
                            else None,
                        )
                    return LLMResponse(
                        content=content,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost,
                    )

                except (RateLimitError, APIConnectionError) as exc:
                    last_error = exc
                    if generation is not None:
                        generation.update(level="ERROR", status_message=type(exc).__name__)
                    if isinstance(exc, RateLimitError) and "perday" in str(exc).lower():
                        raise AgentExecutionError(f"LLM daily quota exhausted: {exc}") from exc
                    time.sleep(2 ** (attempt - 1))
                    continue

                except APIStatusError as exc:
                    if generation is not None:
                        generation.update(level="ERROR", status_message=type(exc).__name__)
                    if exc.status_code >= 500 and attempt < self._max_retries:
                        last_error = exc
                        time.sleep(2 ** (attempt - 1))
                        continue
                    raise AgentExecutionError(f"LLM API error: {exc}") from exc

                except APIError as exc:
                    if generation is not None:
                        generation.update(level="ERROR", status_message=type(exc).__name__)
                    raise AgentExecutionError(f"LLM API error: {exc}") from exc

        raise AgentExecutionError(f"LLM failed after {self._max_retries} retries: {last_error}")
