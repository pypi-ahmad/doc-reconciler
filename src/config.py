"""Process-environment configuration. Values are never logged."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime configuration read from the current process environment.

    Attributes:
        agnes_api_key: Optional Agnes credential; it is never logged.
        agnes_base_url: Fixed Agnes compatible API endpoint.
        agnes_model: Fixed Agnes extraction model.
        ollama_host: Local Ollama service URL without a trailing slash.
        ollama_ocr_model: Local OCR model name.
        max_retries: Maximum supported reconciliation attempts.
    """

    agnes_api_key: str | None
    agnes_base_url: str
    agnes_model: str
    ollama_host: str
    ollama_ocr_model: str
    max_retries: int = 3


def get_settings() -> Settings:
    """Read supported settings from the current process environment.

    Returns:
        Immutable settings with defaults for local Ollama values and the fixed
        Agnes endpoint and model.
    """
    return Settings(
        agnes_api_key=os.environ.get("AGNESAI_API_KEY"),
        agnes_base_url="https://apihub.agnes-ai.com/v1",
        agnes_model="agnes-3.0-flash",
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        ollama_ocr_model=os.environ.get("OLLAMA_OCR_MODEL", "AuditAid/PaddleOCR-VL-1.6-0.9B"),
    )
