"""Text tool library — self-registers at import time."""

from gabriel.tool.library.text.count_words import count_words
from gabriel.tool.library.text.decode_base64 import decode_base64
from gabriel.tool.library.text.encode_base64 import encode_base64
from gabriel.tool.library.text.hash_text import hash_text
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "text.count_words": count_words,
        "text.decode_base64": decode_base64,
        "text.encode_base64": encode_base64,
        "text.hash_text": hash_text,
    }
)

__all__ = ["count_words", "decode_base64", "encode_base64", "hash_text"]
