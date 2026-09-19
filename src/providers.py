"""LLM Provider management following project configuration and hard rules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional
from openai import OpenAI


@dataclass
class ModelOption:
    provider: str
    model_id: str
    display_name: str
    base_url: Optional[str] = None


def get_available_providers() -> List[ModelOption]:
    """Detect available providers based strictly on configured environment variables.

    Never logs or exposes secret keys.
    """
    options: List[ModelOption] = []

    # Default provider: Agnes AI via OpenAI SDK
    if os.environ.get("AGNESAI_API_KEY"):
        options.append(
            ModelOption(
                provider="Agnes AI",
                model_id="agnes-3.0-flash",
                display_name="Agnes AI: agnes-3.0-flash (Default)",
                base_url="https://apihub.agnes-ai.com/v1",
            )
        )

    # Optional extra provider: OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        custom_base = os.environ.get("OPENAI_BASE_URL") or None
        options.append(
            ModelOption(
                provider="OpenAI",
                model_id="gpt-5.6-luna",
                display_name="OpenAI: gpt-5.6-luna",
                base_url=custom_base,
            )
        )
        options.append(
            ModelOption(
                provider="OpenAI",
                model_id="gpt-5.6-terra",
                display_name="OpenAI: gpt-5.6-terra",
                base_url=custom_base,
            )
        )

    # Optional extra provider: Google
    if os.environ.get("GOOGLE_API_KEY"):
        options.append(
            ModelOption(
                provider="Google",
                model_id="gemini-3.5-flash-lite",
                display_name="Google: gemini-3.5-flash-lite",
            )
        )
        options.append(
            ModelOption(
                provider="Google",
                model_id="gemini-3.7-flash",
                display_name="Google: gemini-3.7-flash",
            )
        )

    return options


def get_openai_client(provider_option: ModelOption) -> OpenAI:
    """Create official OpenAI client configured for the selected provider.

    Does not print or store secrets.
    """
    if provider_option.provider == "Agnes AI":
        api_key = os.environ.get("AGNESAI_API_KEY")
        if not api_key:
            raise ValueError("AGNESAI_API_KEY environment variable is missing.")
        return OpenAI(
            api_key=api_key,
            base_url=provider_option.base_url or "https://apihub.agnes-ai.com/v1",
        )
    elif provider_option.provider == "OpenAI":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is missing.")
        return OpenAI(
            api_key=api_key,
            base_url=provider_option.base_url,
        )
    else:
        raise NotImplementedError(f"Provider {provider_option.provider} client initialization requires provider-specific client.")
