"""seed_agent_specs.py — materialize the legacy-migrated agent spec templates.

Phase 4 migration analogue of the legacy ``config/agents.yaml``.

Writes one specification document per template (chat, engineer, researcher,
daemon, server) into a target directory using
:class:`gabriel.agent.store.AgentSpecificationStore`. The resulting files can be
loaded by gabriel-core (for deployment via ``AgentService``) or by the
gabriel-desktop gateway (which reads specs through the same store).

Usage
-----
    python scripts/seed_agent_specs.py --out .gabriel/agent-specs
    python scripts/seed_agent_specs.py --out specs --format yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gabriel.agent.store import AgentSpecificationStore
from gabriel.agent.templates import build_specification, list_templates


def seed_specs(out_dir: str | Path, fmt: str = "json") -> list[Path]:
    """Write every template specification into *out_dir*. Returns paths written."""
    store = AgentSpecificationStore(out_dir, fmt=fmt)
    written: list[Path] = []
    for key in list_templates():
        spec = build_specification(key)
        path = store.save(spec)
        written.append(path)
        print(f"  [+] {key:10s} -> {path}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed migrated agent spec templates.")
    parser.add_argument(
        "--out",
        default=".gabriel/agent-specs",
        help="Output directory for specification files (default: .gabriel/agent-specs).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="json",
        help="Serialization format (default: json).",
    )
    args = parser.parse_args()

    print(f"Seeding {len(list_templates())} agent specification(s) into '{args.out}' ...")
    written = seed_specs(args.out, fmt=args.format)
    print(f"\nDone. {len(written)} specification file(s) written.")


if __name__ == "__main__":
    main()
