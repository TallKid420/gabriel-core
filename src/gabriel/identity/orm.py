from sqlalchemy import JSON, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from datetime import datetime

from gabriel.database.base import Base

class PrincipalORM(Base):
    __tablename__ = "principals"

    principal_id: Mapped[str] = mapped_column(
        String(225), 
        primary_key=True
    ) # principal://...

    org_id: Mapped[str] = mapped_column(
        String(128), 
        ForeignKey("organizations.org_id"), 
        index=True,
        nullable=False
    )

    principal_type: Mapped[str] = mapped_column(
        String(64), 
        nullable=False
    )

    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="active"
    )

    capabilities: Mapped[str] = mapped_column(
        JSON,
        nullable=False,
        server_default="[]"
    ) # list[str]

    resource_grn: Mapped[str | None] = mapped_column(
        String(225),
        nullable=True
    ) # URM mirror link

    resource_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()")
    )