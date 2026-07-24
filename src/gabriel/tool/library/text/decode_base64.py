"""decode_base64 — decode a Base64 string back to UTF-8 text."""

from __future__ import annotations
from langchain_core.tools import tool

import base64


@tool
async def decode_base64(encoded: str) -> dict:
    """Decode a Base64 string back to UTF-8 text.

    Args:
        encoded: A valid Base64-encoded string.

    Returns:
        ``{"encoded", "decoded"}`` on success or ``{"error": ...}``.
    """
    try:
        decoded = base64.b64decode(encoded.encode()).decode()
        return {"encoded": encoded, "decoded": decoded}
    except Exception as exc:
        return {"error": str(exc)}
