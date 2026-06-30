"""Core document subsystem.

Lives in **Core (Platform Layer)**. A Document is a first-class Resource.

This package owns:
- :class:`Document` — a Resource subclass representing an ingested document.
- :class:`DocumentNormalizer` — format-agnostic content normalization
  (migrated and cleaned from the prototype's Docling pipeline). It contains
  NO chat, LLM, or UI logic — only deterministic text extraction.
- :class:`DocumentIngestionService` — orchestrates normalization, mints a GRN,
  and emits a ``resource_created`` event so the Event Store records the fact.
"""
from gabriel.document.models import Document
from gabriel.document.normalizer import DocumentNormalizer, NormalizationError
from gabriel.document.service import DocumentIngestionService, IngestedDocument
from gabriel.document.content_store import ContentStore, DiskContentStore

__all__ = [
    "Document",
    "DocumentNormalizer",
    "NormalizationError",
    "DocumentIngestionService",
    "IngestedDocument",
    "ContentStore",
    "DiskContentStore",
]
