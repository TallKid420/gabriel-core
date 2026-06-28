from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin


class OrganizationORM(Base, GabrielResourceMixin):
    __tablename__ = "organizations"

    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)