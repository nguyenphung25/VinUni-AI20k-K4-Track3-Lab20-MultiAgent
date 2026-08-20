"""Local timing plus optional Langfuse/LangSmith remote tracing."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from time import perf_counter
from typing import Any, Literal

from multi_agent_research_lab.core.config import Settings, get_settings

ObservationType = Literal[
    "span", "agent", "tool", "chain", "retriever", "evaluator", "guardrail", "generation"
]

_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "password", "secret", "token")


def _redact_sensitive(value: Any) -> Any:
    """Recursively redact common credential fields before telemetry export."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
            else _redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive(item) for item in value)
    return value


def _mask_sensitive(*, data: Any, **_kwargs: dict[str, Any]) -> Any:
    """Adapt recursive redaction to the Langfuse MaskFunction protocol."""
    return _redact_sensitive(data)


def configure_remote_tracing(settings: Settings) -> str | None:
    """Configure Langfuse first, with LangSmith retained as a fallback."""
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
        os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url
        os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = settings.app_env
        return "langfuse"
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
        return "langsmith"
    return None


@lru_cache(maxsize=1)
def _get_langfuse_client() -> Any | None:
    """Initialize the SDK lazily, after `.env` settings have been loaded."""
    settings = get_settings()
    if configure_remote_tracing(settings) != "langfuse":
        return None
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        mask=_mask_sensitive,
    )


@contextmanager
def remote_observation(
    *,
    name: str,
    as_type: ObservationType = "span",
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    model_parameters: dict[str, Any] | None = None,
    enabled: bool = True,
) -> Iterator[Any | None]:
    """Create a typed Langfuse observation or a no-op context when disabled."""
    client = _get_langfuse_client() if enabled else None
    if client is None:
        yield None
        return
    with client.start_as_current_observation(
        name=name,
        as_type=as_type,
        input=_redact_sensitive(input),
        metadata=_redact_sensitive(metadata),
        model=model,
        model_parameters=model_parameters,
    ) as observation:
        yield observation


@contextmanager
def remote_trace_attributes(
    *, trace_name: str, tags: list[str], metadata: dict[str, Any], enabled: bool = True
) -> Iterator[None]:
    """Apply stable, filterable attributes to the active Langfuse trace."""
    if not enabled or _get_langfuse_client() is None:
        yield
        return
    from langfuse import propagate_attributes

    with propagate_attributes(
        trace_name=trace_name,
        tags=tags,
        metadata=_redact_sensitive(metadata),
        environment=get_settings().app_env,
    ):
        yield


def current_trace_url() -> str | None:
    """Return a private UI URL for the active Langfuse trace."""
    client = _get_langfuse_client()
    return client.get_trace_url() if client is not None else None


def flush_remote_tracing() -> None:
    """Flush queued events in short-lived CLI processes."""
    client = _get_langfuse_client()
    if client is not None:
        client.flush()


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Measure a named operation for the local JSON trace."""

    started = perf_counter()
    span: dict[str, Any] = {"name": name, "attributes": attributes or {}, "duration_seconds": None}
    try:
        yield span
    finally:
        span["duration_seconds"] = perf_counter() - started
