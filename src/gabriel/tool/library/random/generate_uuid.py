"""generate_uuid — generate a random UUID v4."""

from __future__ import annotations

import uuid


async def generate_uuid() -> dict:
    """Generate a random UUID v4.

    Returns:
        ``{"uuid": "<uuid-string>"}``.
    """
    return {"uuid": str(uuid.uuid4())}
