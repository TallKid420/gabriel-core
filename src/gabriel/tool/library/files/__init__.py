"""File tool library — self-registers at import time."""

from gabriel.tool.library.files.find_file import find_file
from gabriel.tool.library.files.search_documents import search_documents
from gabriel.tool.library.files.semantic_search import semantic_search
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "file.find_file": find_file,
        "file.search_documents": search_documents,
        "file.semantic_search": semantic_search,
    }
)

__all__ = ["find_file", "search_documents", "semantic_search"]
