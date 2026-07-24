"""hash_text — hash a string using a standard algorithm."""

from __future__ import annotations
from langchain_core.tools import tool

import hashlib


@tool
async def hash_text(text: str, algorithm: str = "sha256") -> dict:
    """Hash a string using md5, sha1, or sha256.

    Args:
        text:      The input string to hash.
        algorithm: One of ``"md5"``, ``"sha1"``, ``"sha256"`` (default).

    Returns:
        ``{"algorithm", "hash"}`` on success or ``{"error": ...}``.
    """
    algo = algorithm.lower().replace("-", "")
    supported = {"md5", "sha1", "sha256"}
    if algo not in supported:
        return {
            "error": (
                f"Unsupported algorithm '{algorithm}'. "
                f"Choose from: {', '.join(supported)}"
            )
        }
    h = hashlib.new(algo, text.encode()).hexdigest()
    return {"algorithm": algo, "hash": h}
