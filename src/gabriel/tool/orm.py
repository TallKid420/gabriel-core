from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin

from typing import Any


class ToolORM(Base, GabrielResourceMixin):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    safety_level: Mapped[int] = mapped_column(nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(nullable=False)

    # display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # description: Mapped[str | None] = mapped_column(String(1024), nullable=True)