from sqlalchemy import Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin


class AgentORM(Base, GabrielResourceMixin):
    __tablename__ = "agents"

    specification: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
