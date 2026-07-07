from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin


class PolicyORM(Base, GabrielResourceMixin):
    __tablename__ = "policies"

    # Serialized PolicyStatement list.
    statements: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
