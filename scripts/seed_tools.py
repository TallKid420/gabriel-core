"""seed_tools.py — Bootstrap all platform Tool resources for an organisation.

Usage
-----
    python scripts/seed_tools.py --org-id <ORG_ID> [--created-by <PRINCIPAL_ID>]

This script is idempotent: tools that already exist (matched by name + org_id)
are skipped.  Re-running it after adding new platform tools will only insert
the missing rows.

Tool inventory (40 tools)
--------------------------
  SAFE  (15):  calculate, convert_units, roll_dice,
               count_words, encode_base64, decode_base64, hash_text,
               get_time, days_between, get_current_weather,
               generate_uuid, random_choice, random_number,
               ask_question, list_tools

  FILE   (3):  find_file, search_documents, semantic_search

  EMAIL (13):  send_email, list_emails, get_email, draft_email,
               reply_email, forward_email, archive_email, mark_email,
               delete_email, label_email, move_email, search_emails,
               get_thread

  CALENDAR (9): list_calendars, list_events, get_event, create_event,
                update_event, delete_event, find_free_slot,
                accept_invitation, decline_invitation
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.database.session import async_session
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.tool.models import SafetyLevel, ToolCategory
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
# Tool definitions
# ---------------------------------------------------------------------------
# Each entry is a dict whose keys match ToolService.create_tool kwargs.
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


# ---------------------------------------------------------------------------
# Core seed function
# ---------------------------------------------------------------------------


async def seed_tools(
    *,
    org_id: str,
    created_by: str,
    session_factory: async_sessionmaker[AsyncSession] = async_session,
) -> dict[str, int]:
    """Upsert all platform tools for *org_id*.

    Returns a dict with keys ``created`` and ``skipped``.
    """
    created = 0
    skipped = 0

    async with session_factory() as session:
        service = ToolService(ToolRepository(session))

        for tool_def in _PLATFORM_TOOLS:
            # Check if a tool with this name already exists for the org.
            existing = await service.get_tool_by_name(org_id, tool_def["name"])
            if existing is not None:
                skipped += 1
                continue

            try:
                await service.create_tool(
                    org_id=org_id,
                    created_by=created_by,
                    **tool_def,
                )
                created += 1
                print(f"  [+] {tool_def['name']} ({tool_def['category'].value})")
            except DuplicateResourceError:
                skipped += 1
                print(f"  [~] {tool_def['name']} already exists — skipped")

    return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> None:
    print(f"Seeding tools for org_id='{args.org_id}' created_by='{args.created_by}' ...")
    counts = await seed_tools(org_id=args.org_id, created_by=args.created_by)
    total = counts["created"] + counts["skipped"]
    print(
        f"\nDone. {counts['created']} tool(s) created, "
        f"{counts['skipped']} skipped ({total} total in manifest)."
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
