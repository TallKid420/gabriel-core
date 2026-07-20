"""seed_tools.py — Synchronize discovered platform tools into an org's catalog.

Usage
-----
    python scripts/seed_tools.py --org-id <ORG_ID> [--created-by <PRINCIPAL_ID>]

The set of tools is no longer a hard-coded registry: it is derived from
:data:`gabriel.tool.discovery.tool_indexer`, which walks
``src/gabriel/tool/library`` (plus any third-party ``gabriel.tools`` entry
points) at call time. This script's only remaining job is to keep the
per-organization ``Tool`` database rows in sync with that catalog:

* A tool present in the catalog but missing for the org is created, and
  enabled by default (new organizations start with every prebuilt tool on).
* A tool that already has a row for the org has its descriptive fields
  (description, schemas, category, safety level, required capabilities,
  runtime binding) refreshed, but its ``enabled`` flag is left untouched —
  an operator's manual enable/disable toggle is never overwritten by a
  re-sync.

``_TOOL_METADATA`` below only supplies the handful of fields that cannot be
derived from a function's signature/docstring (category, safety level,
required capabilities, and richer input/output JSON Schemas than
``inspect``-based inference can produce). Tools with no metadata entry still
get seeded, using conservative defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.database.session import async_session
from gabriel.logging_config import configure_logging, get_logger
configure_logging()
logger = get_logger(__name__)

from gabriel.agent.grn_bindings import tool_grn
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.tool.discovery import tool_indexer
from gabriel.tool.models import SafetyLevel, Tool, ToolCategory
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}
_OBJ = {"type": "object"}
_ANY = {}


def _obj(*required: str, **props: dict) -> dict[str, Any]:
    """Build a minimal JSON Schema object definition."""
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = list(required)
    return schema


def _result(**props: dict) -> dict[str, Any]:
    """Convenience: output schema with a 'result' field."""
    return _obj(**props)


# ---------------------------------------------------------------------------
# Tool metadata overrides
# ---------------------------------------------------------------------------
# The catalog of *which* tools exist comes from ``tool_indexer.discover()``
# at sync time. This table only supplies fields the indexer cannot derive
# from a function's signature/docstring (category, safety level, required
# capabilities, and hand-written schemas richer than signature inference).
# Entries are keyed by bare tool name; a discovered tool with no entry here
# still gets seeded, using the conservative defaults in ``_sync_org_tools``.
# ---------------------------------------------------------------------------

_PLATFORM_TOOLS: list[dict[str, Any]] = [
    # ================================================================
    # MATH (3)
    # ================================================================
    {
        "name": "calculate",
        "description": "Safely evaluate a mathematical expression (e.g. 'sqrt(2) + 3').",
        "category": ToolCategory.MATH,
        "input_schema": _obj("expression", expression=_STR),
        "output_schema": _obj(
            result=_NUM,
            expression=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "math.calculate",
    },
    {
        "name": "convert_units",
        "description": "Convert a value from one unit to another (e.g. km → miles).",
        "category": ToolCategory.MATH,
        "input_schema": _obj(
            "value", "from_unit", "to_unit",
            value=_NUM,
            from_unit=_STR,
            to_unit=_STR,
        ),
        "output_schema": _obj(
            result=_NUM,
            from_unit=_STR,
            to_unit=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "math.convert_units",
    },
    {
        "name": "roll_dice",
        "description": "Roll one or more dice and return the results (e.g. '2d6').",
        "category": ToolCategory.MATH,
        "input_schema": _obj(
            "notation",
            notation={"type": "string", "description": "Dice notation such as '2d6' or '1d20'."},
        ),
        "output_schema": _obj(
            rolls={"type": "array", "items": _INT},
            total=_INT,
            notation=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "math.roll_dice",
    },
    # ================================================================
    # TEXT (4)
    # ================================================================
    {
        "name": "count_words",
        "description": "Count the number of words in a string.",
        "category": ToolCategory.TEXT,
        "input_schema": _obj("text", text=_STR),
        "output_schema": _obj(word_count=_INT, text=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "text.count_words",
    },
    {
        "name": "encode_base64",
        "description": "Encode a string to Base64.",
        "category": ToolCategory.TEXT,
        "input_schema": _obj("text", text=_STR),
        "output_schema": _obj(encoded=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "text.encode_base64",
    },
    {
        "name": "decode_base64",
        "description": "Decode a Base64-encoded string.",
        "category": ToolCategory.TEXT,
        "input_schema": _obj("encoded", encoded=_STR),
        "output_schema": _obj(decoded=_STR, error=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "text.decode_base64",
    },
    {
        "name": "hash_text",
        "description": "Hash a string using a chosen algorithm (sha256 by default).",
        "category": ToolCategory.TEXT,
        "input_schema": _obj(
            "text",
            text=_STR,
            algorithm={
                "type": "string",
                "enum": ["md5", "sha1", "sha256", "sha512"],
                "default": "sha256",
            },
        ),
        "output_schema": _obj(hash=_STR, algorithm=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "text.hash_text",
    },
    # ================================================================
    # TIME (3)
    # ================================================================
    {
        "name": "get_time",
        "description": "Return the current date and time in a given timezone.",
        "category": ToolCategory.TIME,
        "input_schema": _obj(
            timezone={
                "type": "string",
                "description": "IANA timezone name, e.g. 'America/New_York'. Defaults to UTC.",
                "default": "UTC",
            }
        ),
        "output_schema": _obj(
            datetime=_STR,
            timezone=_STR,
            unix_timestamp=_NUM,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "time.get_time",
    },
    {
        "name": "days_between",
        "description": "Calculate the number of calendar days between two ISO-8601 dates.",
        "category": ToolCategory.TIME,
        "input_schema": _obj(
            "start_date", "end_date",
            start_date={"type": "string", "format": "date"},
            end_date={"type": "string", "format": "date"},
        ),
        "output_schema": _obj(days=_INT, start_date=_STR, end_date=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "time.days_between",
    },
    {
        "name": "get_current_weather",
        "description": "Fetch current weather conditions for a city.",
        "category": ToolCategory.TIME,
        "input_schema": _obj("city", city=_STR),
        "output_schema": _obj(
            city=_STR,
            temperature_c=_NUM,
            condition=_STR,
            humidity_pct=_NUM,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "time.get_current_weather",
    },
    # ================================================================
    # RANDOM (3)
    # ================================================================
    {
        "name": "generate_uuid",
        "description": "Generate a random UUID v4.",
        "category": ToolCategory.RANDOM,
        "input_schema": _obj(),
        "output_schema": _obj(uuid=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "random.generate_uuid",
    },
    {
        "name": "random_choice",
        "description": "Pick a random item from a list.",
        "category": ToolCategory.RANDOM,
        "input_schema": _obj(
            "items",
            items={"type": "array", "items": {}, "minItems": 1},
        ),
        "output_schema": _obj(choice=_ANY),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "random.random_choice",
    },
    {
        "name": "random_number",
        "description": "Generate a random integer within a specified range.",
        "category": ToolCategory.RANDOM,
        "input_schema": _obj(
            "min_value", "max_value",
            min_value=_INT,
            max_value=_INT,
        ),
        "output_schema": _obj(number=_INT, min_value=_INT, max_value=_INT),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "random.random_number",
    },
    # ================================================================
    # UTILITY (2)
    # ================================================================
    {
        "name": "ask_question",
        "description": "Pause agent execution and ask the user a clarifying question.",
        "category": ToolCategory.UTILITY,
        "input_schema": _obj("question", question=_STR),
        "output_schema": _obj(question=_STR, answer=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "utility.ask_question",
    },
    {
        "name": "list_tools",
        "description": "List all tools available to the calling agent, optionally filtered by category.",
        "category": ToolCategory.UTILITY,
        "input_schema": _obj(
            category={
                "type": "string",
                "description": "Optional category filter.",
            }
        ),
        "output_schema": _obj(
            tools={"type": "array", "items": _OBJ},
            count=_INT,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke"],
        "runtime_binding": "utility.list_tools",
    },
    # ================================================================
    # FILE (3)
    # ================================================================
    {
        "name": "find_file",
        "description": "Search for files in the org's document store by glob pattern.",
        "category": ToolCategory.FILE,
        "input_schema": _obj("pattern", pattern=_STR),
        "output_schema": _obj(
            matches={"type": "array", "items": _STR},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "file:read"],
        "runtime_binding": "file.find_file",
    },
    {
        "name": "search_documents",
        "description": "Full-text keyword search across the org's document store.",
        "category": ToolCategory.FILE,
        "input_schema": _obj("query", query=_STR, limit=_INT),
        "output_schema": _obj(
            results={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "file:read"],
        "runtime_binding": "file.search_documents",
    },
    {
        "name": "semantic_search",
        "description": "Semantic (vector) search across the org's document store.",
        "category": ToolCategory.FILE,
        "input_schema": _obj("query", query=_STR, top_k=_INT),
        "output_schema": _obj(
            results={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "file:read"],
        "runtime_binding": "file.semantic_search",
    },
    # ================================================================
    # EMAIL — 13 tools  (SafetyLevel: READ=SAFE, WRITE=REQUIRES_CONFIRMATION)
    # ================================================================
    {
        "name": "send_email",
        "description": "Send an email on behalf of the org's connected email account.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "to", "subject", "body",
            to=_STR,
            subject=_STR,
            body=_STR,
        ),
        "output_schema": _obj(status=_STR, to=_STR, error=_STR),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.send_email",
    },
    {
        "name": "list_emails",
        "description": "List recent emails from the inbox with optional folder filter.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            folder=_STR,
            limit=_INT,
        ),
        "output_schema": _obj(
            emails={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.list_emails",
    },
    {
        "name": "get_email",
        "description": "Retrieve the full content of a specific email by UID.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj("uid", uid=_STR, folder=_STR),
        "output_schema": _obj(
            uid=_STR,
            subject=_STR,
            sender=_STR,
            body=_STR,
            date=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.get_email",
    },
    {
        "name": "draft_email",
        "description": "Create a draft email without sending it.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "to", "subject", "body",
            to=_STR, subject=_STR, body=_STR,
        ),
        "output_schema": _obj(status=_STR, draft_uid=_STR, error=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.draft_email",
    },
    {
        "name": "reply_email",
        "description": "Reply to an existing email by UID.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "uid", "body",
            uid=_STR, body=_STR, folder=_STR,
        ),
        "output_schema": _obj(status=_STR, in_reply_to=_STR, error=_STR),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.reply_email",
    },
    {
        "name": "forward_email",
        "description": "Forward an email to another recipient.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "uid", "to",
            uid=_STR, to=_STR, folder=_STR, note=_STR,
        ),
        "output_schema": _obj(status=_STR, to=_STR, error=_STR),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.forward_email",
    },
    {
        "name": "archive_email",
        "description": "Archive (move to Archive folder) an email by UID.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj("uid", uid=_STR, folder=_STR),
        "output_schema": _obj(status=_STR, uid=_STR, error=_STR),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.archive_email",
    },
    {
        "name": "mark_email",
        "description": "Mark an email as read or unread.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "uid", "mark_as",
            uid=_STR,
            mark_as={
                "type": "string",
                "enum": ["read", "unread"],
                "description": "Whether to mark the email as 'read' or 'unread'.",
            },
            folder=_STR,
        ),
        "output_schema": _obj(status=_STR, uid=_STR, mark_as=_STR, error=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.mark_email",
    },
    {
        "name": "delete_email",
        "description": "Permanently delete an email by UID.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj("uid", uid=_STR, folder=_STR),
        "output_schema": _obj(status=_STR, uid=_STR, error=_STR),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.delete_email",
    },
    {
        "name": "label_email",
        "description": "Add or remove an IMAP label/flag on an email.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "uid", "label", "action",
            uid=_STR,
            label=_STR,
            action={"type": "string", "enum": ["add", "remove"]},
            folder=_STR,
        ),
        "output_schema": _obj(status=_STR, uid=_STR, label=_STR, action=_STR, error=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.label_email",
    },
    {
        "name": "move_email",
        "description": "Move an email from one folder/mailbox to another.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            "uid", "destination",
            uid=_STR,
            destination=_STR,
            source=_STR,
        ),
        "output_schema": _obj(status=_STR, uid=_STR, destination=_STR, error=_STR),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.move_email",
    },
    {
        "name": "search_emails",
        "description": "Search emails by keyword, sender, subject, or date range.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj(
            query=_STR, folder=_STR, limit=_INT,
        ),
        "output_schema": _obj(
            emails={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.search_emails",
    },
    {
        "name": "get_thread",
        "description": "Retrieve all messages in an email thread by thread ID or reference UID.",
        "category": ToolCategory.EMAIL,
        "input_schema": _obj("thread_id", thread_id=_STR, folder=_STR),
        "output_schema": _obj(
            messages={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.gmail.get_thread",
    },
    # ================================================================
    # CALENDAR — 9 tools
    # ================================================================
    {
        "name": "list_calendars",
        "description": "List all Google Calendars accessible to the authenticated user.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(),
        "output_schema": _obj(
            calendars={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.list_calendars",
    },
    {
        "name": "list_events",
        "description": "List upcoming events from a Google Calendar within a date range.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(
            calendar_id=_STR,
            time_min={"type": "string", "format": "date-time"},
            time_max={"type": "string", "format": "date-time"},
            max_results=_INT,
        ),
        "output_schema": _obj(
            events={"type": "array", "items": _OBJ},
            count=_INT,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.list_events",
    },
    {
        "name": "get_event",
        "description": "Retrieve the full details of a single Google Calendar event.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj("event_id", event_id=_STR, calendar_id=_STR),
        "output_schema": _obj(
            event=_OBJ,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.get_event",
    },
    {
        "name": "create_event",
        "description": "Create a new event on a Google Calendar.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(
            "summary", "start_time", "end_time",
            summary=_STR,
            start_time={"type": "string", "format": "date-time"},
            end_time={"type": "string", "format": "date-time"},
            calendar_id=_STR,
            description=_STR,
            location=_STR,
            attendees={"type": "array", "items": _STR},
        ),
        "output_schema": _obj(
            success=_BOOL,
            event_id=_STR,
            html_link=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.create_event",
    },
    {
        "name": "update_event",
        "description": "Update an existing Google Calendar event.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(
            "event_id",
            event_id=_STR,
            calendar_id=_STR,
            summary=_STR,
            start_time={"type": "string", "format": "date-time"},
            end_time={"type": "string", "format": "date-time"},
            description=_STR,
            location=_STR,
        ),
        "output_schema": _obj(
            success=_BOOL,
            event_id=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.update_event",
    },
    {
        "name": "delete_event",
        "description": "Delete a Google Calendar event.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj("event_id", event_id=_STR, calendar_id=_STR),
        "output_schema": _obj(
            success=_BOOL,
            event_id=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.delete_event",
    },
    {
        "name": "find_free_slot",
        "description": "Find the next available free time slot in a calendar.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(
            "duration_minutes",
            duration_minutes=_INT,
            calendar_id=_STR,
            search_from={"type": "string", "format": "date-time"},
            search_until={"type": "string", "format": "date-time"},
        ),
        "output_schema": _obj(
            found=_BOOL,
            start=_STR,
            end=_STR,
            error=_STR,
        ),
        "safety_level": SafetyLevel.SAFE,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.find_free_slot",
    },
    {
        "name": "accept_invitation",
        "description": "Accept a Google Calendar event invitation.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(
            "event_id",
            event_id=_STR,
            calendar_id=_STR,
            comment=_STR,
        ),
        "output_schema": _obj(
            success=_BOOL,
            event_id=_STR,
            status=_STR,
            message=_STR,
        ),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.accept_invitation",
    },
    {
        "name": "decline_invitation",
        "description": "Decline a Google Calendar event invitation.",
        "category": ToolCategory.CALENDAR,
        "input_schema": _obj(
            "event_id",
            event_id=_STR,
            calendar_id=_STR,
            comment=_STR,
        ),
        "output_schema": _obj(
            success=_BOOL,
            event_id=_STR,
            status=_STR,
            message=_STR,
        ),
        "safety_level": SafetyLevel.REQUIRES_CONFIRMATION,
        "required_capabilities": ["tool:invoke", "integration:read"],
        "runtime_binding": "integration.google_calendar.decline_invitation",
    },
]

_METADATA_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in _PLATFORM_TOOLS}


# ---------------------------------------------------------------------------
# Core sync function
# ---------------------------------------------------------------------------


def _resolve_fields(discovered: Tool) -> dict[str, Any]:
    """Merge a discovered tool with its (optional) metadata override."""
    meta = _METADATA_BY_NAME.get(discovered.name, {})
    return {
        "description": discovered.description or meta.get("description", ""),
        "category": meta.get("category", ToolCategory.UTILITY),
        "parameters": meta.get("input_schema", discovered.parameters),
        "safety_level": meta.get("safety_level", SafetyLevel.SAFE),
        "runtime_binding": discovered.runtime_binding,
    }


async def seed_tools(
    *,
    org_id: str,
    created_by: str,
    session_factory: async_sessionmaker[AsyncSession] = async_session,
) -> dict[str, int]:
    """Synchronize the discovered tool catalog with *org_id*'s ``Tool`` rows.

    New tools are created and enabled by default. Tools that already have a
    row for the org are refreshed (description, schemas, category, safety
    level, required capabilities, runtime binding) but their existing
    ``enabled`` toggle is preserved — this call never re-enables or disables
    a tool an operator has explicitly toggled.

    Returns a dict with keys ``created`` and ``updated``.
    """
    created = 0
    updated = 0

    catalog = tool_indexer.discover()

    async with session_factory() as session:
        service = ToolService(ToolRepository(session))

        for discovered in catalog:
            fields = _resolve_fields(discovered)
            existing = await service.get_tool_by_name(org_id, discovered.name)

            if existing is None:
                try:
                    await service.create_tool(
                        org_id=org_id,
                        created_by=created_by,
                        name=discovered.name,
                        enabled=True,
                        tool_grn=tool_grn(discovered.name, org_id, version=1),
                        **fields,
                    )
                    created += 1
                    logger.info("  [+] %s (%s)", discovered.name, fields["category"].value)
                except DuplicateResourceError:
                    logger.info("  [~] %s already exists - skipped", discovered.name)
                continue

            await service.update_tool(
                str(existing.grn),
                updated_by=created_by,
                **fields,
            )
            updated += 1
            logger.info("  [~] %s refreshed (enabled=%s)", discovered.name, existing.enabled)

    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> None:
    logger.info("Seeding tools for org_id='%s' created_by='%s' ...", args.org_id, args.created_by)
    counts = await seed_tools(org_id=args.org_id, created_by=args.created_by)
    total = counts["created"] + counts["updated"]
    logger.info(
        "Done. %s tool(s) created, %s refreshed (%s total in catalog).",
        counts["created"],
        counts["updated"],
        total,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap platform Tool resources for an organisation."
    )
    parser.add_argument("--org-id", required=True, help="Target organisation ID.")
    parser.add_argument(
        "--created-by",
        default="system:seed_tools",
        help="Principal ID recorded as the creator (default: 'system:seed_tools').",
    )
    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
