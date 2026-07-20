"""SQLAlchemy ORM model for the Tool resource."""

from typing import Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin


class ToolORM(Base, GabrielResourceMixin):
    """Persistence representation of a :class:`~gabriel.tool.models.Tool`.

    Mirrors :class:`GabrielResourceMixin` columns (grn, org_id, resource_type,
    state, version, timestamps, metadata, labels) plus tool-specific fields.

    ``category`` and ``safety_level`` are stored as their raw primitive values
    (string / int) so the schema stays stable if enum members are renamed.
    The mapper layer converts to/from :class:`ToolCategory` / :class:`SafetyLevel`.
    """

    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Stored as the enum's string value (e.g. "math", "email")
    category: Mapped[str] = mapped_column(String(64), nullable=False)

    # Input schema for the function in each python script.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Stored as int (0 = SAFE, 1 = REQUIRES_CONFIRMATION, 2 = RESTRICTED)
    safety_level: Mapped[int] = mapped_column(nullable=False, default=0)

    # Dot-path key resolved by FunctionRegistry / ToolExecutor at runtime.
    # e.g. "math.calculate", "integration.gmail.send_email"
    runtime_binding: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Declared execution location (enum string value: local/enterprise/cloud/edge).
    # V1 is declaration-only — no runtime routing consumes this yet.
    execution_runtime: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local"
    )

    # Org-level kill switch: a disabled tool is never exposed to the chat runtime.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Free-form tool-specific configuration (never secrets).
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
