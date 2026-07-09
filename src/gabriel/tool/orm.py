"""SQLAlchemy ORM model for the Tool resource."""

from typing import Any

from sqlalchemy import JSON, String
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

    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    output_schema: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Stored as int (0 = SAFE, 1 = REQUIRES_CONFIRMATION, 2 = RESTRICTED)
    safety_level: Mapped[int] = mapped_column(nullable=False, default=0)

    required_capabilities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # Dot-path key resolved by FunctionRegistry / ToolExecutor at runtime.
    # e.g. "math.calculate", "integration.gmail.send_email"
    runtime_binding: Mapped[str] = mapped_column(String(255), nullable=False, default="")
