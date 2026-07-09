"""encode_base64 — encode a UTF-8 string to Base64."""

from __future__ import annotations

import base64


async def encode_base64(text: str) -> dict:
    """Encode a UTF-8 string to Base64.

    Args:
        text: The input string to encode.

    Returns:
        ``{"original", "encoded"}``.
    """
    encoded = base64.b64encode(text.encode()).decode()
    return {"original": text, "encoded": encoded}
