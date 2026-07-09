"""File-based persistence for :class:`AgentSpecification` documents.

Gabriel Core already persists deployed agents as *resources* in Postgres
(see :class:`gabriel.agent.service.AgentService` and ``AgentRepository``).
That is the system of record for **deployed** agents.

This module adds a lightweight, dependency-free persistence layer for the
**specification documents themselves** — the declarative blueprints produced by
the template library. It is the migration analogue of the legacy
``config/agents.yaml`` file: a place to author, version, and load specs before
they are deployed, and to export/import them between environments.

Two on-disk formats are supported:

* JSON  — one ``<name>.json`` file per spec (always available).
* YAML  — one ``<name>.yaml`` file per spec, mirroring legacy ``agents.yaml``
          (requires PyYAML; degrades gracefully if unavailable).

The store is intentionally simple and synchronous: it is used at author/deploy
time, not on the hot execution path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gabriel.agent.specification import AgentSpecification

try:  # PyYAML is optional
    import yaml  # type: ignore

    _HAS_YAML = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_YAML = False


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_stem(name: str) -> str:
    """Sanitize a spec name into a filesystem-safe file stem."""
    stem = _SAFE_NAME_RE.sub("-", name.strip()).strip("-")
    if not stem:
        raise ValueError(f"Cannot derive a safe filename from name {name!r}")
    return stem


class SpecificationNotFoundError(FileNotFoundError):
    """Raised when a requested specification does not exist in the store."""


class AgentSpecificationStore:
    """Persist and load :class:`AgentSpecification` documents on disk.

    Args:
        root: Directory under which specification files are stored. Created
              (including parents) on first use if it does not exist.
        fmt:  Default serialization format, ``"json"`` (default) or ``"yaml"``.
    """

    def __init__(self, root: str | Path, fmt: str = "json") -> None:
        self.root = Path(root)
        if fmt not in ("json", "yaml"):
            raise ValueError("fmt must be 'json' or 'yaml'")
        if fmt == "yaml" and not _HAS_YAML:
            raise RuntimeError("PyYAML is not installed; cannot use fmt='yaml'")
        self.fmt = fmt

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str, fmt: str | None = None) -> Path:
        """Return the on-disk path for a spec *name* in the given format."""
        fmt = fmt or self.fmt
        ext = "json" if fmt == "json" else "yaml"
        return self.root / f"{_safe_stem(name)}.{ext}"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def save(
        self,
        spec: AgentSpecification,
        *,
        name: str | None = None,
        fmt: str | None = None,
    ) -> Path:
        """Persist *spec* to disk and return the path written.

        Args:
            spec: The specification to persist.
            name: Optional override for the file stem (defaults to ``spec.name``).
            fmt:  Optional per-call format override.
        """
        fmt = fmt or self.fmt
        if fmt == "yaml" and not _HAS_YAML:
            raise RuntimeError("PyYAML is not installed; cannot save as YAML")

        self._ensure_root()
        path = self.path_for(name or spec.name, fmt)
        payload = spec.model_dump(mode="json")

        if fmt == "json":
            path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
        else:  # yaml
            path.write_text(
                yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
        return path

    def save_many(self, specs: list[AgentSpecification], fmt: str | None = None) -> list[Path]:
        """Persist a batch of specifications; returns the paths written."""
        return [self.save(spec, fmt=fmt) for spec in specs]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    @staticmethod
    def _deserialize(text: str, fmt: str) -> dict:
        if fmt == "json":
            return json.loads(text)
        if not _HAS_YAML:
            raise RuntimeError("PyYAML is not installed; cannot read YAML")
        return yaml.safe_load(text)

    def load(self, name: str) -> AgentSpecification:
        """Load a specification by *name*.

        Tries the store's default format first, then the other format, so a
        store can transparently read both ``.json`` and ``.yaml`` files.

        Raises:
            SpecificationNotFoundError: if no matching file exists.
        """
        candidates = [
            (self.path_for(name, "json"), "json"),
            (self.path_for(name, "yaml"), "yaml"),
        ]
        # Prefer the configured default format first.
        if self.fmt == "yaml":
            candidates.reverse()

        for path, fmt in candidates:
            if path.exists():
                data = self._deserialize(path.read_text(encoding="utf-8"), fmt)
                return AgentSpecification.model_validate(data)

        raise SpecificationNotFoundError(
            f"No specification named {name!r} found under {self.root}"
        )

    def load_all(self) -> dict[str, AgentSpecification]:
        """Load every specification in the store, keyed by spec name."""
        specs: dict[str, AgentSpecification] = {}
        if not self.root.exists():
            return specs
        for path in sorted(self.root.iterdir()):
            if path.suffix.lstrip(".") not in ("json", "yaml", "yml"):
                continue
            fmt = "json" if path.suffix == ".json" else "yaml"
            try:
                data = self._deserialize(path.read_text(encoding="utf-8"), fmt)
                spec = AgentSpecification.model_validate(data)
                specs[spec.name] = spec
            except Exception:  # skip unrelated / malformed files
                continue
        return specs

    # ------------------------------------------------------------------
    # List / delete / exists
    # ------------------------------------------------------------------
    def list(self) -> list[str]:
        """Return the file stems of all persisted specifications."""
        if not self.root.exists():
            return []
        stems = {
            p.stem
            for p in self.root.iterdir()
            if p.suffix.lstrip(".") in ("json", "yaml", "yml")
        }
        return sorted(stems)

    def exists(self, name: str) -> bool:
        """Return True if a spec named *name* is persisted in either format."""
        return self.path_for(name, "json").exists() or self.path_for(name, "yaml").exists()

    def delete(self, name: str) -> None:
        """Delete a persisted specification (both formats if present)."""
        removed = False
        for fmt in ("json", "yaml"):
            path = self.path_for(name, fmt)
            if path.exists():
                path.unlink()
                removed = True
        if not removed:
            raise SpecificationNotFoundError(
                f"No specification named {name!r} found under {self.root}"
            )
