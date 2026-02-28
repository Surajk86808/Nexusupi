"""
Organisation model: top-level tenant entity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Organisation(UUIDMixin, TimestampMixin, Base):
    """
    Organisation (tenant) model.

    All tenant-scoped entities (users, credit transactions, etc.) will
    reference this table via organisation_id.
    """

    __tablename__ = "organisations"

    # Attributes
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

