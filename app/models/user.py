"""
User model: identity entity scoped to one organisation.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.organisation import Organisation


class UserRole(str, Enum):
    """Allowed user roles."""

    ADMIN = "admin"
    MEMBER = "member"


class User(UUIDMixin, TimestampMixin, Base):
    """Application user identity model."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    google_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(
            UserRole,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="user_role",
        ),
        nullable=False,
    )

    organisation: Mapped["Organisation"] = relationship(
        "Organisation",
        back_populates="users",
    )
