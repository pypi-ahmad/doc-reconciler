"""Agnes client configuration using the official OpenAI Python SDK."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from openai import APIStatusError, OpenAI, RateLimitError

DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_AGNES_MODEL = "agnes-3.0-flash"


@dataclass(frozen=True)
class ProviderConfig:
    """Describe the single supported Agnes provider.

    Attributes:
        provider: Human-readable provider name accepted by compatibility helpers.
        model_id: Fixed Agnes model used for extraction and retry patches.
        display_name: UI-friendly provider and model label.
        api_key_env: Environment variable that supplies the API key.
        base_url: Fixed compatible OpenAI API endpoint.
    """

    provider: str = "Agnes AI"
    model_id: str = DEFAULT_AGNES_MODEL
    display_name: str = f"Agnes AI: {DEFAULT_AGNES_MODEL}"
    api_key_env: str = "AGNESAI_API_KEY"
    base_url: str = DEFAULT_AGNES_BASE_URL


def get_agnes_client(api_key: str | None = None) -> OpenAI:
    """Build the fixed Agnes client without logging or persisting its key.

    Args:
        api_key: Optional caller-supplied key. When omitted, the value comes
            from ``AGNESAI_API_KEY`` in the current process environment.

    Returns:
        An OpenAI SDK client configured for the fixed Agnes endpoint.

    Raises:
        ValueError: If neither ``api_key`` nor the environment variable exists.
    """
    key = api_key or os.environ.get("AGNESAI_API_KEY")
    if not key:
        raise ValueError(
            "Required environment variable AGNESAI_API_KEY is unavailable; "
            "relaunch the host if it was recently configured."
        )
    return OpenAI(api_key=key, base_url=DEFAULT_AGNES_BASE_URL)


def get_available_providers() -> list[ProviderConfig]:
    """Return Agnes only when its process environment key is present.

    Returns:
        A one-element Agnes configuration list, or an empty list when the key
        is unavailable.
    """
    return [ProviderConfig()] if os.environ.get("AGNESAI_API_KEY") else []


def get_provider_client(config: ProviderConfig) -> OpenAI:
    """Create the client for a compatible Agnes provider configuration.

    Args:
        config: Provider configuration returned by ``get_available_providers``.

    Returns:
        The fixed Agnes OpenAI SDK client.

    Raises:
        ValueError: If the provider name or model differs from Agnes Flash.
    """
    if config.provider != "Agnes AI" or config.model_id != DEFAULT_AGNES_MODEL:
        raise ValueError("Only Agnes AI agnes-3.0-flash is supported.")
    return get_agnes_client()


def create_chat_completion(
    messages: list[dict[str, Any]],
    *,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
    max_429_retries: int = 3,
) -> Any:
    """Create one completion, retrying HTTP 429 responses with bounded backoff.

    Args:
        messages: OpenAI-compatible chat messages.
        client: Optional preconfigured client, primarily useful for tests.
        model: Agnes model identifier.
        max_429_retries: Number of retries after the first rate-limited request.

    Returns:
        The SDK completion response.

    Raises:
        RateLimitError: If every allowed attempt receives HTTP 429.
        APIStatusError: If the provider returns a non-retriable API error.
    """
    active_client = client or get_agnes_client()
    for retry in range(max_429_retries + 1):
        try:
            return active_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
            )
        except RateLimitError:
            if retry == max_429_retries:
                raise
        except APIStatusError as error:
            if error.status_code != 429 or retry == max_429_retries:
                raise
        time.sleep(2**retry)
    raise RuntimeError("Agnes 429 retry loop ended unexpectedly.")
