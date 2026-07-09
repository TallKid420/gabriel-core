"""count_words — count words, characters, and sentences in a block of text."""

from __future__ import annotations

import re


async def count_words(text: str) -> dict:
    """Count words, characters, and sentences in a block of text.

    Args:
        text: The input string to analyse.

    Returns:
        ``{"words", "characters", "characters_no_spaces", "sentences"}``.
    """
    words = len(text.split())
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", ""))
    sentences = len(re.findall(r"[.!?]+", text))
    return {
        "words": words,
        "characters": chars,
        "characters_no_spaces": chars_no_spaces,
        "sentences": sentences,
    }
