from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class UserORM(Base, GabrielResourceMixin):
    """Persistence model for the User resource.

    Email uniqueness is enforced per organization (multi-tenant: the same
    email may exist in two different orgs, but only once within one).
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    principal_id: Mapped[str] = mapped_column(
        String(225), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
