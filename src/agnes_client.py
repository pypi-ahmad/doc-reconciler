"""Agnes AI client helper and provider configuration.

Base URL: https://apihub.agnes-ai.com/v1
Default model: agnes-3.0-flash
Environment variable: AGNESAI_API_KEY (read from user env, never committed or logged)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv
from openai import OpenAI

# Load local .env if present (names/keys managed by user)
load_dotenv()

DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_AGNES_MODEL = "agnes-3.0-flash"


@dataclass
class ProviderConfig:
    provider: str
    model_id: str
    display_name: str
    api_key_env: str
    base_url: Optional[str] = None


def get_agnes_client(api_key: Optional[str] = None) -> OpenAI:
    """Create official OpenAI Python SDK client targeting Agnes AI endpoint."""
    key = api_key or os.environ.get("AGNESAI_API_KEY")
    if not key:
        raise ValueError(
            "Missing AGNESAI_API_KEY. Please set the AGNESAI_API_KEY environment variable."
        )
    return OpenAI(
        api_key=key,
        base_url=DEFAULT_AGNES_BASE_URL,
    )


def get_available_providers() -> List[ProviderConfig]:
    """Detect available LLM providers from environment variables without exposing values."""
    providers: List[ProviderConfig] = []

    # 1. Agnes AI (Primary default)
    if os.environ.get("AGNESAI_API_KEY"):
        providers.append(
            ProviderConfig(
                provider="Agnes AI",
                model_id=DEFAULT_AGNES_MODEL,
                display_name=f"Agnes AI: {DEFAULT_AGNES_MODEL} (Default)",
                api_key_env="AGNESAI_API_KEY",
                base_url=DEFAULT_AGNES_BASE_URL,
            )
        )

    # 2. OpenAI provider
    if os.environ.get("OPENAI_API_KEY"):
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        providers.extend([
            ProviderConfig(
                provider="OpenAI",
                model_id="gpt-5.6-luna",
                display_name="OpenAI: gpt-5.6-luna",
                api_key_env="OPENAI_API_KEY",
                base_url=base_url,
            ),
            ProviderConfig(
                provider="OpenAI",
                model_id="gpt-5.6-terra",
                display_name="OpenAI: gpt-5.6-terra",
                api_key_env="OPENAI_API_KEY",
                base_url=base_url,
            ),
        ])

    # 3. Google Gemini provider
    if os.environ.get("GOOGLE_API_KEY"):
        providers.extend([
            ProviderConfig(
                provider="Google",
                model_id="gemini-3.5-flash-lite",
                display_name="Google: gemini-3.5-flash-lite",
                api_key_env="GOOGLE_API_KEY",
            ),
            ProviderConfig(
                provider="Google",
                model_id="gemini-3.7-flash",
                display_name="Google: gemini-3.7-flash",
                api_key_env="GOOGLE_API_KEY",
            ),
        ])

    return providers


def get_provider_client(config: ProviderConfig) -> OpenAI:
    """Instantiate OpenAI client for the given provider configuration."""
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise ValueError(f"Environment variable {config.api_key_env} is not set.")

    kwargs: dict = {"api_key": api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url

    return OpenAI(**kwargs)
