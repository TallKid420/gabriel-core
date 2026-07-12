from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, utcnow


class OrgMembershipORM(Base):
    """A principal's seat within an organization, carrying its role.

    Membership is the join between identity (Principal / User) and tenancy
    (Organization). The role recorded here drives the capability set granted
    to the member's principal (see ``gabriel.identity.roles``).
    """

    __tablename__ = "org_memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "principal_id", name="uq_membership_org_principal"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    principal_id: Mapped[str] = mapped_column(String(225), index=True, nullable=False)
    user_grn: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
