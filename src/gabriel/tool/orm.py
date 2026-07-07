from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin


class ToolORM(Base, GabrielResourceMixin):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    safety_level: Mapped[int] = mapped_column(nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)