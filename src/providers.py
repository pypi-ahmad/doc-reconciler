"""Compatibility exports for the fixed Agnes provider."""

from src.agnes_client import (
    ProviderConfig as ModelOption,
)
from src.agnes_client import (
    get_available_providers,
)
from src.agnes_client import (
    get_provider_client as get_openai_client,
)

__all__ = ["ModelOption", "get_available_providers", "get_openai_client"]
