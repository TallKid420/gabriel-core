from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gabriel.database.session import async_session
from gabriel.logging_config import configure_logging, get_logger
from gabriel.policy.models import Effect, PolicyStatement
from gabriel.policy.repository import PolicyRepository
from gabriel.policy.service import PolicyService
from gabriel.resource.exceptions import ResourceNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


configure_logging()
logger = get_logger(__name__)


@dataclass(frozen=True)
class LegacyToolDecision:
    decision: str
    principal_match: str
    tool_match: str


def _normalize_decision(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized not in {"allow", "ask", "deny"}:
        raise ValueError(f"Unsupported decision '{raw}'")
    return normalized


def _tool_to_resource_match(tool: str) -> str:
    if tool.startswith("grn:"):
        return tool
    return f"grn:*:tool/{tool}:*"


def _looks_like_principal(value: str) -> bool:
    return value.startswith("principal://") or value == "*"


def _coerce_tools(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    raise ValueError(f"Unsupported tool mapping payload: {value!r}")


def _parse_decision_block(decision: str, payload: Any) -> list[LegacyToolDecision]:
    rows: list[LegacyToolDecision] = []
    normalized = _normalize_decision(decision)

    if isinstance(payload, dict):
        for key, value in payload.items():
            key_str = str(key)
            if _looks_like_principal(key_str):
                for tool in _coerce_tools(value):
                    rows.append(
                        LegacyToolDecision(
                            decision=normalized,
                            principal_match=key_str,
                            tool_match=tool,
                        )
                    )
                continue

            # Fallback: treat as tool -> principal(s) shape.
            principals = _coerce_tools(value)
            for principal in principals:
                rows.append(
                    LegacyToolDecision(
                        decision=normalized,
                        principal_match=principal,
                        tool_match=key_str,
                    )
                )
        return rows

    for tool in _coerce_tools(payload):
        rows.append(
            LegacyToolDecision(
                decision=normalized,
                principal_match="*",
                tool_match=tool,
            )
        )
    return rows


def _parse_gate_dict(payload: dict[Any, Any]) -> list[LegacyToolDecision]:
    rows: list[LegacyToolDecision] = []
    for key, value in payload.items():
        key_str = str(key)
        if isinstance(value, str):
            # tool -> DECISION
            rows.extend(_parse_decision_block(value, [key_str]))
            continue

        if isinstance(value, dict):
            # tool -> {principal -> DECISION}
            for principal, decision in value.items():
                rows.extend(
                    _parse_decision_block(
                        str(decision),
                        {str(principal): [key_str]},
                    )
                )
            continue

        raise ValueError(f"Unsupported gate mapping for '{key_str}': {value!r}")
    return rows


def parse_legacy_gate(path: str | Path) -> list[LegacyToolDecision]:
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Legacy gate file not found: {source_path}")

    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    constants: dict[str, Any] = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        try:
            constants[node.targets[0].id] = ast.literal_eval(node.value)
        except Exception:
            continue

    rows: list[LegacyToolDecision] = []

    for decision_name in ("ALLOW", "ASK", "DENY"):
        if decision_name in constants:
            rows.extend(_parse_decision_block(decision_name, constants[decision_name]))

    if rows:
        return rows

    for gate_name in (
        "LEGACY_GATE",
        "TOOL_GATE",
        "GATE",
        "TOOL_PERMISSIONS",
    ):
        gate_payload = constants.get(gate_name)
        if isinstance(gate_payload, dict):
            rows.extend(_parse_gate_dict(gate_payload))
            break

    if not rows:
        raise ValueError(
            "No legacy ALLOW/ASK/DENY mappings were found in gate file. "
            "Expected ALLOW/ASK/DENY or LEGACY_GATE/TOOL_GATE dictionary constants."
        )

    return rows


def _build_statements(mappings: list[LegacyToolDecision], decision: str) -> list[PolicyStatement]:
    statements: list[PolicyStatement] = []
    effect = Effect.ALLOW if decision == "allow" else Effect.DENY

    for mapping in mappings:
        if mapping.decision != decision:
            continue
        statements.append(
            PolicyStatement(
                effect=effect,
                principal_match=mapping.principal_match,
                action_match="tool:invoke",
                resource_match=_tool_to_resource_match(mapping.tool_match),
                condition="legacy:ask" if decision == "ask" else None,
            )
        )
    return statements


async def _upsert_policy(
    service: PolicyService,
    *,
    org_id: str,
    created_by: str,
    policy_grn: str,
    statements: list[PolicyStatement],
    source_gate: str,
) -> None:
    try:
        await service.get_policy(policy_grn)
    except ResourceNotFoundError:
        await service.create_policy(
            org_id=org_id,
            created_by=created_by,
            statements=statements,
            policy_grn=policy_grn,
            metadata={"source": source_gate},
            labels={"seed": "legacy-gate"},
        )
        return

    await service.update_policy(
        policy_grn,
        updated_by=created_by,
        statements=statements,
    )


async def seed_legacy_policies(
    *,
    gate_path: str | Path,
    org_id: str,
    created_by: str,
    session_factory: async_sessionmaker[AsyncSession] = async_session,
) -> dict[str, int]:
    mappings = parse_legacy_gate(gate_path)
    source_gate = str(Path(gate_path))

    grouped: dict[str, list[LegacyToolDecision]] = defaultdict(list)
    for mapping in mappings:
        grouped[mapping.decision].append(mapping)

    counts = {
        "allow": len(grouped.get("allow", [])),
        "ask": len(grouped.get("ask", [])),
        "deny": len(grouped.get("deny", [])),
    }

    async with session_factory() as session:
        service = PolicyService(PolicyRepository(session))

        for decision in ("allow", "ask", "deny"):
            statements = _build_statements(mappings, decision)
            if not statements:
                continue
            await _upsert_policy(
                service,
                org_id=org_id,
                created_by=created_by,
                policy_grn=f"grn:{org_id}:policy/legacy-gate-{decision}:1",
                statements=statements,
                source_gate=source_gate,
            )

    return counts


async def _async_main(args: argparse.Namespace) -> None:
    counts = await seed_legacy_policies(
        gate_path=args.gate_path,
        org_id=args.org_id,
        created_by=args.created_by,
    )
    logger.info(
        "Seeded legacy policies (allow=%s, ask=%s, deny=%s)",
        counts["allow"],
        counts["ask"],
        counts["deny"],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed legacy gate ALLOW/ASK/DENY mappings into core Policy resources.",
    )
    parser.add_argument("--gate-path", required=True, help="Path to legacy gate.py file")
    parser.add_argument("--org-id", default="core", help="Organization to own seeded policies")
    parser.add_argument(
        "--created-by",
        default="principal://core/system/seed-legacy-policies",
        help="Principal ID used as the policy creator",
    )
    return parser


def main() -> None:
    import asyncio

    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
