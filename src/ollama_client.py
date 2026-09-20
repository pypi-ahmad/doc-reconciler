"""Ollama client for local OCR and vision table extraction."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "AuditAid/PaddleOCR-VL-1.6-0.9B"


def get_ollama_host() -> str:
    """Return the configured Ollama host URL without a trailing slash.

    Returns:
        ``OLLAMA_HOST`` when set, otherwise the local default host.
    """
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).strip()
    return host.rstrip("/")


def is_ollama_available(
    host: str | None = None, model: str = DEFAULT_OLLAMA_MODEL
) -> tuple[bool, str]:
    """Check whether Ollama is running and has the requested OCR model.

    Args:
        host: Optional Ollama host override.
        model: Required OCR model name or tag.

    Returns:
        A pair of availability state and a safe diagnostic message.
    """
    target_host = (host or get_ollama_host()).rstrip("/")
    url = f"{target_host}/api/tags"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "doc-reconciler/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            # Match model name with or without tag (e.g. :latest)
            has_model = any(
                m == model or m.startswith(f"{model}:") or model.startswith(m) for m in models
            )
            if has_model:
                return True, f"Ollama running with model '{model}'."
            message = (
                f"Ollama running at {target_host}, but model '{model}' is not installed. "
                f"Installed: {', '.join(models) or 'none'}. Run: ollama run {model}"
            )
            return False, message
    except urllib.error.URLError as e:
        return False, f"Cannot connect to Ollama at {target_host}: {e.reason}"
    except Exception as e:  # noqa: BLE001 - health check must degrade to a warning
        return False, f"Ollama health check error: {e}"


def extract_tables_with_ollama(
    image_path: str,
    prompt: str = "Extract all text and tables from this document page accurately as markdown format.",
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str | None = None,
    timeout: float = 120.0,
) -> str:
    """Extract text and tables from a rendered page image using Ollama.

    Args:
        image_path: Absolute or relative path to the PNG image.
        prompt: Instruction for the vision/OCR model.
        model: Ollama vision/OCR model tag.
        host: Optional Ollama host URL.
        timeout: Request timeout in seconds.

    Returns:
        Extracted markdown string.

    Raises:
        FileNotFoundError: If the rendered page image does not exist.
        RuntimeError: If the Ollama service or image extraction request fails.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Page image not found: {image_path}")

    target_host = (host or get_ollama_host()).rstrip("/")
    url = f"{target_host}/api/generate"

    with open(image_path, "rb") as f:
        img_bytes = f.read()
    b64_img = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64_img],
        "stream": False,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "doc-reconciler/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Failed to communicate with Ollama at {target_host} for model '{model}': {e.reason}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Ollama table extraction failed for '{image_path}': {e}") from e
