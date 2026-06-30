"""Document normalization for Core.

Migrated and refactored from the prototype's ``daemon/document.py``.

Design notes / layer boundary:
- This is **Core (Platform Layer)** infrastructure. It converts an uploaded
  document of any supported format into normalized Markdown text.
- It deliberately contains NO chat logic, NO LLM prompts, and NO UI. It only
  performs deterministic extraction.
- ``docling`` is the preferred high-fidelity converter but is an OPTIONAL
  dependency. If it is unavailable (or fails), we fall back to lightweight,
  per-extension extractors. The fallback for plain text formats has no third
  party dependencies so the Core ingestion path always works.
"""
from __future__ import annotations

from pathlib import Path


class NormalizationError(Exception):
    """Raised when a document cannot be normalized by any available strategy."""


# Extensions the lightweight fallback can handle without optional heavy deps.
_PLAINTEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".log"}


class DocumentNormalizer:
    """Convert documents to normalized Markdown/plain text.

    Supported (via docling when installed):
        .txt .md .pdf .docx .html .csv images spreadsheets

    Supported (always, via fallback):
        .txt .md .html .csv .pdf (PyMuPDF) .docx (python-docx) when their
        libraries are present; plain-text formats need no extra libraries.
    """

    def normalize(self, path: str | Path) -> str:
        """Normalize a document to text, preferring docling with a fallback.

        Args:
            path: Filesystem path to the document.

        Returns:
            Normalized text (Markdown where possible).

        Raises:
            NormalizationError: If no strategy can extract content.
        """
        path = Path(path)
        if not path.exists():
            raise NormalizationError(f"Document not found: {path}")

        # 1. Preferred: docling autodetect (high fidelity, optional dependency).
        try:
            return self._docling(path)
        except Exception:
            # Any docling failure (incl. ImportError) falls through to backup.
            pass

        # 2. Fallback: per-extension lightweight extraction.
        try:
            return self._fallback(path)
        except NormalizationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise NormalizationError(
                f"Failed to normalize {path.name}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------
    def _docling(self, path: Path) -> str:
        """High-fidelity conversion using docling (optional dependency)."""
        from docling.document_converter import DocumentConverter  # type: ignore

        converter = DocumentConverter()
        result = converter.convert(path)
        return result.document.export_to_markdown()

    def _fallback(self, path: Path) -> str:
        """Lightweight extraction keyed on file extension."""
        ext = path.suffix.lower()

        if ext in _PLAINTEXT_EXTS:
            return path.read_text(encoding="utf-8")

        if ext == ".html" or ext == ".htm":
            try:
                from bs4 import BeautifulSoup  # type: ignore

                soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
                return soup.get_text("\n")
            except ImportError:
                # Crude tag strip if bs4 is unavailable.
                import re

                raw = path.read_text(encoding="utf-8")
                return re.sub(r"<[^>]+>", "", raw)

        if ext == ".csv":
            # Stdlib CSV -> simple text table (no pandas dependency required).
            import csv

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            return "\n".join(", ".join(row) for row in rows)

        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF  # type: ignore

                with fitz.open(str(path)) as pdf:
                    return "\n".join(page.get_text() for page in pdf)
            except ImportError as exc:
                raise NormalizationError(
                    "PDF normalization requires 'docling' or 'PyMuPDF'"
                ) from exc

        if ext == ".docx":
            try:
                from docx import Document as DocxDocument  # type: ignore

                doc = DocxDocument(str(path))
                return "\n".join(p.text for p in doc.paragraphs)
            except ImportError as exc:
                raise NormalizationError(
                    "DOCX normalization requires 'docling' or 'python-docx'"
                ) from exc

        raise NormalizationError(
            f"Unsupported document type '{ext}' for {path.name}"
        )
